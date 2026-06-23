import json

from typing import Optional, Any

import psycopg2

class ActionLedger:

    """Tracks which external-facing actions have already run to

    completion for a given thread, so the orchestrator can check

    before acting instead of guessing after the fact."""

    def __init__(self, dsn: str):

        self.dsn = dsn

    def already_completed(

        self, thread_id: str, action_name: str, sequence: int

    ) -> Optional[Any]:

        with psycopg2.connect(self.dsn) as conn:

            with conn.cursor() as cur:

                cur.execute(

                    """

                    SELECT result_payload FROM completed_actions

                    WHERE thread_id = %s AND action_name = %s AND sequence = %s

                    """,

                    (thread_id, action_name, sequence),

                )

                row = cur.fetchone()

                return row[0] if row else None

    def mark_completed(

        self, thread_id: str, action_name: str, sequence: int, result: dict

    ) -> None:

        with psycopg2.connect(self.dsn) as conn:

            with conn.cursor() as cur:

                cur.execute(

                    """

                    INSERT INTO completed_actions

                        (thread_id, action_name, sequence, result_payload)

                    VALUES (%s, %s, %s, %s)

                    ON CONFLICT (thread_id, action_name, sequence) DO NOTHING

                    """,

                    (thread_id, action_name, sequence, json.dumps(result)),

                )

class SendConfirmationEmailState:

    name = "send_confirmation_email"

    def __init__(self, email_service, ledger: ActionLedger):

        self.email_service = email_service

        self.ledger = ledger

    def run(self, context) -> None:

        sequence = len(context.history)

        cached_result = self.ledger.already_completed(

            context.thread_id, self.name, sequence

        )

        if cached_result is not None:

            # Already sent. Skip the network call entirely and move on

            # as if the action had just succeeded, because it did.

            context.transition_to(ResolvedState())

            return

        result = self.email_service.send_refund_confirmation(

            customer_id=context.customer_id, order_id=context.order_id

        )

        self.ledger.mark_completed(context.thread_id, self.name, sequence, result)

        context.transition_to(ResolvedState())
