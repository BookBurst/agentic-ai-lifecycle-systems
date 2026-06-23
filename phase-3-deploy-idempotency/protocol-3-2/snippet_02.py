import json

from typing import Optional, Any

import psycopg2

class IntentLog:

    """Durably records what an agent is about to do, before it does it.

    This is the record that survives a crash even when the tool call

    itself never gets the chance to."""

    def __init__(self, dsn: str):

        self.dsn = dsn

    def record_intent(

        self,

        thread_id: str,

        action_name: str,

        sequence: int,

        agent_id: str,

        model_version: str,

        reasoning_summary: str,

        tool_name: str,

        tool_parameters: dict,

    ) -> None:

        # This write must complete and commit BEFORE the tool call below

        # ever fires. No buffering, no async fire-and-forget. If this

        # insert fails, the tool call does not happen.

        with psycopg2.connect(self.dsn) as conn:

            with conn.cursor() as cur:

                cur.execute(

                    """

                    INSERT INTO agent_intent_log

                        (thread_id, action_name, sequence, agent_id,

                         model_version, reasoning_summary, tool_name, tool_parameters)

                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)

                    ON CONFLICT (thread_id, action_name, sequence) DO NOTHING

                    """,

                    (

                        thread_id, action_name, sequence, agent_id,

                        model_version, reasoning_summary, tool_name,

                        json.dumps(tool_parameters),

                    ),

                )

    def resolve_intent(

        self, thread_id: str, action_name: str, sequence: int, status: str

    ) -> None:

        with psycopg2.connect(self.dsn) as conn:

            with conn.cursor() as cur:

                cur.execute(

                    """

                    UPDATE agent_intent_log

                    SET status = %s, resolved_at = now()

                    WHERE thread_id = %s AND action_name = %s AND sequence = %s

                    """,

                    (status, thread_id, action_name, sequence),

                )

class ChargePaymentState:

    name = "charge_payment"

    def __init__(self, gateway: "PaymentGateway", intent_log: IntentLog, ledger: "ActionLedger"):

        self.gateway = gateway

        self.intent_log = intent_log

        self.ledger = ledger

    def run(self, context) -> None:

        sequence = len(context.history)

        if self.ledger.already_completed(context.thread_id, self.name, sequence):

            context.transition_to(ResolvedState())

            return

        # Step 1: the intent gets written and committed FIRST.

        self.intent_log.record_intent(

            thread_id=context.thread_id,

            action_name=self.name,

            sequence=sequence,

            agent_id=context.agent_id,

            model_version=context.model_version,

            reasoning_summary="Order validated, amount under approval threshold, proceeding to charge.",

            tool_name="charge_customer",

            tool_parameters={"amount_cents": context.amount_cents, "customer_id": context.customer_id},

        )

        try:

            # Step 2: only now does the tool actually run.

            result = self.gateway.charge_customer(

                context.thread_id, sequence, context.amount_cents, context.customer_id

            )

            self.intent_log.resolve_intent(context.thread_id, self.name, sequence, "completed")

            self.ledger.mark_completed(context.thread_id, self.name, sequence, result.__dict__)

            context.transition_to(ResolvedState())

        except RuntimeError:

            self.intent_log.resolve_intent(context.thread_id, self.name, sequence, "failed")

            raise
