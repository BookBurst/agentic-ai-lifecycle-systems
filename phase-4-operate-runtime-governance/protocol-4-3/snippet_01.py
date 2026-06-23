from __future__ import annotations

import json

import uuid

from dataclasses import dataclass, asdict

from datetime import datetime, timedelta, timezone

from enum import Enum

from typing import Any

import psycopg2

class ApprovalStatus(str, Enum):

    PENDING   = "pending"

    APPROVED  = "approved"

    REJECTED  = "rejected"

    TIMED_OUT = "timed_out"

class HumanApprovalRequired(Exception):

    """

    Signals that a high-risk node has paused execution and is waiting

    for an explicit human decision. This is not a failure: the FSM

    boundary handler must catch it, record the approval_id on the

    thread checkpoint, and exit the execution loop cleanly.

    """

    def __init__(self, approval_id: str, thread_id: str) -> None:

        self.approval_id = approval_id

        self.thread_id   = thread_id

        super().__init__(

            f"Thread '{thread_id}' paused at approval gate "

            f"(approval_id: '{approval_id}'). Awaiting human review."

        )

@dataclass

class PendingApproval:

    """

    The complete snapshot written to PostgreSQL when execution pauses.

    action_payload  -- The specific parameters the human is being asked to approve.

    workflow_state  -- Full FSM snapshot for deterministic resume after approval.

    Both fields must be populated before the gate fires.

    """

    approval_id:    str

    thread_id:      str

    created_at:     datetime

    expires_at:     datetime

    status:         ApprovalStatus

    action_type:    str

    action_payload: dict[str, Any]

    workflow_state: dict[str, Any]

    reviewer_notes: str = ""

    def is_expired(self) -> bool:

        return datetime.now(timezone.utc) > self.expires_at

APPROVAL_TIMEOUT_HOURS = 24

class ApprovalGate:

    """

    Implements the interrupt_before pattern for a designated high-risk FSM node.

    On first pass:  persists the PendingApproval record and raises

                    HumanApprovalRequired. Execution halts; server resources

                    are released. The workflow does not proceed.

    On resume pass: the FSM reloads thread state and re-enters the same node.

                    The node reads the approval status from state and either

                    executes the action (APPROVED) or raises (REJECTED/TIMED_OUT).

    """

    def __init__(self, conn: psycopg2.extensions.connection) -> None:

        self._conn = conn

    def pause_for_review(

        self,

        thread_id:      str,

        action_type:    str,

        action_payload: dict[str, Any],

        workflow_state: dict[str, Any],

    ) -> None:

        """

        Serialize state and raise HumanApprovalRequired.

        This method never returns normally on first pass.

        """

        now      = datetime.now(timezone.utc)

        approval = PendingApproval(

            approval_id    = str(uuid.uuid4()),

            thread_id      = thread_id,

            created_at     = now,

            expires_at     = now + timedelta(hours=APPROVAL_TIMEOUT_HOURS),

            status         = ApprovalStatus.PENDING,

            action_type    = action_type,

            action_payload = action_payload,

            workflow_state = workflow_state,

        )

        self._persist(approval)

        raise HumanApprovalRequired(

            approval_id=approval.approval_id,

            thread_id=thread_id,

        )

    def _persist(self, approval: PendingApproval) -> None:

        with self._conn.cursor() as cur:

            cur.execute(

                """

                INSERT INTO pending_approvals (

                    approval_id, thread_id, created_at, expires_at,

                    status, action_type, action_payload, workflow_state

                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)

                """,

                (

                    approval.approval_id,

                    approval.thread_id,

                    approval.created_at,

                    approval.expires_at,

                    approval.status.value,

                    approval.action_type,

                    json.dumps(approval.action_payload),

                    json.dumps(approval.workflow_state),

                ),

            )

        self._conn.commit()

# ---------------------------------------------------------------------------

# The two-pass FSM node pattern.

# On first entry: no approval exists yet, gate fires and pauses.

# On resume entry: approval status is injected into state, gate reads it.

# ---------------------------------------------------------------------------

def wire_transfer_node(

    state: dict[str, Any],

    gate:  ApprovalGate,

) -> dict[str, Any]:

    """

    High-risk financial node. Always requires explicit human approval.

    First pass: state carries no approval_status -> gate pauses execution.

    Resume pass: state carries approval_status set by the orchestrator

                 after the human's decision was recorded.

    """

    approval_status = state.get("approval_status")

    if approval_status == ApprovalStatus.APPROVED:

        # Human approved. Execute the action and return updated state.

        return execute_wire_transfer(state)

    if approval_status in (ApprovalStatus.REJECTED, ApprovalStatus.TIMED_OUT):

        raise ValueError(

            f"Wire transfer for thread '{state['thread_id']}' was "

            f"{approval_status.value}. Halting execution."

        )

    # No approval on record. Pause for human review.

    gate.pause_for_review(

        thread_id      = state["thread_id"],

        action_type    = "wire_transfer",

        action_payload = {

            "recipient_account": state["transfer_recipient"],

            "amount_usd":        state["transfer_amount"],

            "reference":         state["transfer_reference"],

        },

        workflow_state = state,

    )
