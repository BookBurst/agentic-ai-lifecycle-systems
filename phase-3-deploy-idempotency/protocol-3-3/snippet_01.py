from enum import Enum

from typing import Callable, List, Optional

class StepType(str, Enum):

    COMPENSABLE = "COMPENSABLE"

    PIVOT = "PIVOT"

    RETRYABLE = "RETRYABLE"

class SagaStep:

    def __init__(

        self,

        name: str,

        step_type: StepType,

        forward: Callable,

        compensate: Optional[Callable] = None,

        max_retries: int = 5,

    ):

        self.name = name

        self.step_type = step_type

        self.forward = forward

        self.compensate = compensate

        self.max_retries = max_retries

        if step_type == StepType.COMPENSABLE and compensate is None:

            raise ValueError(f"'{name}' is COMPENSABLE but has no compensating action defined")

class SagaExecutionFailed(Exception):

    pass

class SagaOrchestrator:

    """Runs a fixed sequence of steps. Failure before the pivot

    triggers LIFO compensation of every step that already succeeded.

    Failure at or after the pivot stops the saga and demands human

    review, since rollback is no longer a safe option at that point."""

    def __init__(self, steps: List[SagaStep]):

        self.steps = steps

        pivots = [s for s in steps if s.step_type == StepType.PIVOT]

        if len(pivots) != 1:

            raise ValueError("A saga must define exactly one pivot step")

        self.pivot_index = steps.index(pivots[0])

    def execute(self, context) -> None:

        completed_compensable: List[SagaStep] = []

        for index, step in enumerate(self.steps):

            try:

                if step.step_type == StepType.RETRYABLE:

                    self._execute_with_retry(step, context)

                else:

                    step.forward(context)

            except Exception as error:

                if index < self.pivot_index:

                    self._compensate(completed_compensable, context)

                    raise SagaExecutionFailed(

                        f"Step '{step.name}' failed before the pivot. "

                        f"Rolled back {len(completed_compensable)} prior step(s)."

                    ) from error

                raise SagaExecutionFailed(

                    f"Step '{step.name}' failed after the pivot. "

                    f"Rollback is not safe here, this thread needs human review."

                ) from error

            if step.step_type == StepType.COMPENSABLE:

                completed_compensable.append(step)

    def _execute_with_retry(self, step: SagaStep, context) -> None:

        last_error = None

        for attempt in range(1, step.max_retries + 1):

            try:

                step.forward(context)

                return

            except Exception as error:

                last_error = error

                continue

        raise last_error

    def _compensate(self, completed_steps: List[SagaStep], context) -> None:

        # LIFO: undo the most recently completed step first.

        for step in reversed(completed_steps):

            step.compensate(context)

order_fulfillment_saga = SagaOrchestrator(steps=[

    SagaStep(

        name="reserve_inventory",

        step_type=StepType.COMPENSABLE,

        forward=lambda ctx: inventory_service.reserve(ctx.order_id, ctx.items),

        compensate=lambda ctx: inventory_service.release(ctx.order_id, ctx.items),

    ),

    SagaStep(

        name="charge_customer",

        step_type=StepType.COMPENSABLE,

        forward=lambda ctx: payment_gateway.charge_customer(

            ctx.thread_id, ctx.sequence, ctx.amount_cents, ctx.customer_id

        ),

        compensate=lambda ctx: payment_gateway.refund_customer(ctx.thread_id, ctx.charge_id),

    ),

    SagaStep(

        name="dispatch_to_warehouse",

        step_type=StepType.PIVOT,

        forward=lambda ctx: warehouse_service.dispatch(ctx.order_id),

    ),

    SagaStep(

        name="send_shipment_confirmation",

        step_type=StepType.RETRYABLE,

        forward=lambda ctx: email_service.send_shipment_confirmation(ctx.customer_id, ctx.order_id),

    ),

])
