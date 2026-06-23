def test_manager_rejection_returns_to_input():

    context = WorkflowContext(thread_id="t-001")

    context.current_state = PendingApprovalState()

    context.process_event(WorkflowEvent(name="manager_rejected"))

    assert isinstance(context.current_state, AwaitingInputState)

    assert context.history[-1] == "awaiting_input"
