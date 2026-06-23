import psycopg2

from psycopg2.extras import Json

STATE_REGISTRY = {

    "awaiting_input": AwaitingInputState,

    "validating_order": ValidatingOrderState,

    "pending_approval": PendingApprovalState,

    "resolved": ResolvedState,

}

class CheckpointNotFoundError(Exception):

    pass

class UnknownStateError(Exception):

    pass

class PostgresCheckpointStore:

    """Persists and rehydrates WorkflowContext state on every transition.

    A thread that has not been checkpointed is, as far as recovery is

    concerned, a thread that never happened. Every write here is meant

    to run synchronously, before the orchestration layer triggers

    whatever comes next.

    """

    def __init__(self, dsn: str):

        self._dsn = dsn

    def save(self, context: "WorkflowContext") -> None:

        with psycopg2.connect(self._dsn) as conn:

            with conn.cursor() as cur:

                cur.execute(

                    """

                    INSERT INTO workflow_checkpoints

                        (thread_id, current_state, context_data, history, updated_at)

                    VALUES (%s, %s, %s, %s, now())

                    ON CONFLICT (thread_id) DO UPDATE SET

                        current_state = EXCLUDED.current_state,

                        context_data = EXCLUDED.context_data,

                        history = EXCLUDED.history,

                        updated_at = now()

                    """,

                    (

                        context.thread_id,

                        context.current_state.name,

                        Json({

                            "order_id": context.order_id,

                            "approval_threshold": context.approval_threshold,

                        }),

                        Json(context.history),

                    ),

                )

    def load(self, thread_id: str) -> "WorkflowContext":

        with psycopg2.connect(self._dsn) as conn:

            with conn.cursor() as cur:

                cur.execute(

                    """

                    SELECT current_state, context_data, history

                    FROM workflow_checkpoints

                    WHERE thread_id = %s

                    """,

                    (thread_id,),

                )

                row = cur.fetchone()

        if row is None:

            raise CheckpointNotFoundError(thread_id)

        state_name, context_data, history = row

        state_cls = STATE_REGISTRY.get(state_name)

        if state_cls is None:

            raise UnknownStateError(state_name)

        context = WorkflowContext(

            thread_id=thread_id,

            approval_threshold=context_data["approval_threshold"],

        )

        context.order_id = context_data.get("order_id")

        context.current_state = state_cls()

        context.history = history

        return context
