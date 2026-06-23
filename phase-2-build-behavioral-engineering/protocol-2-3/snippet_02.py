CONFIDENCE_THRESHOLD = 0.75

class AmbiguousIntentError(Exception):

    pass

class Supervisor:

    def __init__(self, llm_client, worker_registry: dict, max_retries: int = 1):

        self.llm_client = llm_client

        self.worker_registry = worker_registry

        self.max_retries = max_retries

    def route(self, request_text: str):

        attempt = 0

        while attempt <= self.max_retries:

            try:

                decision = self.llm_client.classify(

                    request_text,

                    response_schema=RoutingDecision,

                )

            except SchemaValidationError:

                attempt += 1

                continue

            if decision.confidence < CONFIDENCE_THRESHOLD:

                return ClarificationWorker().execute(request_text, decision)

            worker_cls = self.worker_registry.get(decision.intent)

            if worker_cls is None:

                raise UnroutableRequestError(decision.intent)

            return worker_cls().execute(request_text)

        raise UnroutableRequestError("schema_validation_failed_after_retries")
