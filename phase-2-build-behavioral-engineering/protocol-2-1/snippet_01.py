from abc import ABC, abstractmethod

from dataclasses import dataclass, field

from typing import Optional

@dataclass

class WorkflowEvent:

    name: str

    payload: dict = field(default_factory=dict)

class WorkflowState(ABC):

    """Base class for every stage of the support workflow.

    Each concrete state owns exactly two responsibilities: how to react

    to an incoming event, and which state comes next. Nothing outside

    this class needs to know how that decision gets made.

    """

    name: str = "undefined"

    @abstractmethod

    def handle(self, event: WorkflowEvent, context: "WorkflowContext") -> None:

        ...

class AwaitingInputState(WorkflowState):

    name = "awaiting_input"

    def handle(self, event: WorkflowEvent, context: "WorkflowContext") -> None:

        if event.name == "customer_message_received":

            order_id = event.payload.get("order_id")

            if order_id:

                context.order_id = order_id

                context.transition_to(ValidatingOrderState())

            else:

                context.log("missing_order_id_prompting_customer")

        # Any other event arriving in this state is simply ignored.

        # The model is never asked what to do with it.

class ValidatingOrderState(WorkflowState):

    name = "validating_order"

    def handle(self, event: WorkflowEvent, context: "WorkflowContext") -> None:

        if event.name == "order_lookup_succeeded":

            if event.payload.get("amount", 0) > context.approval_threshold:

                context.transition_to(PendingApprovalState())

            else:

                context.transition_to(ResolvedState())

        elif event.name == "order_lookup_failed":

            context.log("order_not_found_returning_to_input")

            context.transition_to(AwaitingInputState())

class PendingApprovalState(WorkflowState):

    name = "pending_approval"

    def handle(self, event: WorkflowEvent, context: "WorkflowContext") -> None:

        if event.name == "manager_approved":

            context.transition_to(ResolvedState())

        elif event.name == "manager_rejected":

            context.transition_to(AwaitingInputState())

class ResolvedState(WorkflowState):

    name = "resolved"

    def handle(self, event: WorkflowEvent, context: "WorkflowContext") -> None:

        # This is a member of F, the set of final states from the

        # formal definition in Protocol 2.1. No transition leaves here.

        context.log("workflow_already_resolved_ignoring_event")

class WorkflowContext:

    """Holds the thread's current state and nothing else.

    The context never inspects what state it is in. It forwards every

    event to whichever state object is currently active, and records

    every transition for audit purposes.

    """

    def __init__(self, thread_id: str, approval_threshold: float = 500.0):

        self.thread_id = thread_id

        self.approval_threshold = approval_threshold

        self.order_id: Optional[str] = None

        self.current_state: WorkflowState = AwaitingInputState()

        self.history: list[str] = [self.current_state.name]

    def process_event(self, event: WorkflowEvent) -> None:

        self.current_state.handle(event, self)

    def transition_to(self, new_state: WorkflowState) -> None:

        self.log(f"transition_{self.current_state.name}_to_{new_state.name}")

        self.current_state = new_state

        self.history.append(new_state.name)

    def log(self, message: str) -> None:

        print(f"[{self.thread_id}] {message}")
