from enum import Enum

from typing import List

class RecoveryAction(str, Enum):

    SAFE_RETRY = "SAFE_RETRY"

    FREEZE_FOR_HUMAN = "FREEZE_FOR_HUMAN"

    TRIGGER_ROLLBACK = "TRIGGER_ROLLBACK"

# Actions known to be idempotent by construction, e.g. anything that

# ships with a deterministic idempotency key per Protocol 3.1. Keeping

# this as an explicit, hand-maintained set is deliberate: an action is

# safe to auto-retry only because an engineer verified it is, never

# because a model decided it looked safe enough.

IDEMPOTENT_ACTIONS = {"charge_customer"}

class RecoveryRouter:

    """Runs once at process startup, before the workflow is allowed to

    advance. Classifies every in-flight intent with plain rules. There

    is intentionally no language model anywhere in this path."""

    def __init__(self, intent_log, dsn: str):

        self.intent_log = intent_log

        self.dsn = dsn

    def classify(self, pending_record: dict) -> RecoveryAction:

        if pending_record["surrounding_transaction_failed"]:

            return RecoveryAction.TRIGGER_ROLLBACK

        if pending_record["tool_name"] in IDEMPOTENT_ACTIONS:

            return RecoveryAction.SAFE_RETRY

        return RecoveryAction.FREEZE_FOR_HUMAN

    def recover_thread(self, thread_id: str) -> List[dict]:

        pending = self._load_pending_intents(thread_id)

        decisions = [ ]

        for record in pending:

            action = self.classify(record)

            if action == RecoveryAction.SAFE_RETRY:

                # Safe precisely because the idempotency key is identical

                # on this attempt. A duplicate cannot occur downstream.

                self._replay(record)

            elif action == RecoveryAction.FREEZE_FOR_HUMAN:

                self._freeze(thread_id, record)

            elif action == RecoveryAction.TRIGGER_ROLLBACK:

                self._enqueue_rollback(thread_id, record)

            decisions.append({"sequence": record["sequence"], "action": action.value})

        return decisions
