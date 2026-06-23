from enum import Enum

from pydantic import BaseModel

class WorkerIntent(str, Enum):

    REFUND_INQUIRY = "refund_inquiry"

    ACCOUNT_UPDATE = "account_update"

    TECHNICAL_ISSUE = "technical_issue"

class RoutingDecision(BaseModel):

    intent: WorkerIntent

    confidence: float

class UnroutableRequestError(Exception):

    pass

class Supervisor:

    """Reads an incoming request and decides which Worker handles it.

    The Supervisor never drafts a reply, never calls a billing API,

    and never touches a database. Its only output is a routing

    decision, forced through a rigid schema so the model has no room

    to wander into free-form text where a structured choice belongs.

    """

    def __init__(self, llm_client, worker_registry: dict):

        self.llm_client = llm_client

        self.worker_registry = worker_registry

    def route(self, request_text: str):

        decision = self.llm_client.classify(

            request_text,

            response_schema=RoutingDecision,

        )

        worker_cls = self.worker_registry.get(decision.intent)

        if worker_cls is None:

            raise UnroutableRequestError(decision.intent)

        worker = worker_cls()

        return worker.execute(request_text)

worker_registry = {

    WorkerIntent.REFUND_INQUIRY: RefundWorker,

    WorkerIntent.ACCOUNT_UPDATE: AccountUpdateWorker,

    WorkerIntent.TECHNICAL_ISSUE: TechnicalIssueWorker,

}
