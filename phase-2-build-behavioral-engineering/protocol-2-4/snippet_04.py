class WorkflowContext:

    def __init__(self, thread_id, approval_threshold=500.0, checkpoint_store=None):

        self.thread_id = thread_id

        self.approval_threshold = approval_threshold

        self.order_id = None

        self.current_state = AwaitingInputState()

        self.history = [self.current_state.name]

        self.checkpoint_store = checkpoint_store

    def transition_to(self, new_state) -> None:

        self.log(f"transition_{self.current_state.name}_to_{new_state.name}")

        self.current_state = new_state

        self.history.append(new_state.name)

        if self.checkpoint_store:

            self.checkpoint_store.save(self)
