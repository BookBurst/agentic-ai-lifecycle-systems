from dataclasses import dataclass

from datetime import datetime

@dataclass(frozen=True)

class PromptTemplate:

    prompt_id: str

    version: str

    content: str

    last_modified_by: str

    last_modified_at: datetime

class PromptNotFoundError(Exception):

    pass

class PromptRegistry:

    """Resolves a prompt_id and version into a PromptTemplate.

    States never hold prompt text directly. They hold a reference and

    ask the registry to resolve it at the moment they need it.

    """

    def __init__(self, store):

        # store is anything with a fetch(prompt_id, version) method,

        # typically a thin wrapper around a database table.

        self._store = store

        self._cache: dict[tuple[str, str], PromptTemplate] = {}

    def get(self, prompt_id: str, version: str = "pinned") -> PromptTemplate:

        cache_key = (prompt_id, version)

        if cache_key in self._cache:

            return self._cache[cache_key]

        record = self._store.fetch(prompt_id, version)

        if record is None:

            raise PromptNotFoundError(

                f"No prompt found for id={prompt_id!r} version={version!r}"

            )

        template = PromptTemplate(

            prompt_id=record["prompt_id"],

            version=record["resolved_version"],

            content=record["content"],

            last_modified_by=record["modified_by"],

            last_modified_at=record["modified_at"],

        )

        self._cache[cache_key] = template

        return template

    def invalidate(self, prompt_id: str, version: str = "pinned") -> None:

        self._cache.pop((prompt_id, version), None)
