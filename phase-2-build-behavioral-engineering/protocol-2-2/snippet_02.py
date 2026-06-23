class RefundExplainerState(WorkflowState):

    name = "explaining_refund"

    def __init__(self, prompt_registry: PromptRegistry):

        self.prompt_registry = prompt_registry

    def handle(self, event: WorkflowEvent, context: "WorkflowContext") -> None:

        template = self.prompt_registry.get("refund_explainer", version="pinned")

        # template.version and template.last_modified_by get written

        # straight into the execution log for this event, so a

        # postmortem six months from now can answer "which exact

        # wording produced this output" without anyone guessing.

        context.log(

            f"using_prompt={template.prompt_id} "

            f"version={template.version} "

            f"author={template.last_modified_by}"

        )

        context.call_model(template.content, event.payload)
