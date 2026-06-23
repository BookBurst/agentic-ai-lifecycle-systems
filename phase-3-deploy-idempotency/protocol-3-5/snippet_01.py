from __future__ import annotations

from typing import Callable

# A migration function takes a raw checkpoint dict and returns

# a transformed checkpoint dict. It never receives a WorkflowContext

# object -- only the raw data as it came out of PostgreSQL.

MigrationFn = Callable[[dict], dict]

class CheckpointMigrator:

    """

    Applies version migrations to checkpoint data at load time.

    Migrations are registered as pure functions: dict in, dict out.

    They chain linearly -- v1 -> v2 -> v3, never v1 -> v3 directly.

    This means each function only needs to know about one version

    transition, and adding a new version requires adding one function.

    The migrator never modifies the database. The caller (load()) is

    responsible for writing the migrated data back during the next save.

    """

    def __init__(self, current_version: str) -> None:

        self._current = current_version

        self._registry: dict[tuple[str, str], MigrationFn] = {}

    def register(

        self, from_version: str, to_version: str, fn: MigrationFn

    ) -> None:

        self._registry[(from_version, to_version)] = fn

    def migrate(self, raw: dict) -> dict:

        """

        Applies all necessary migration functions in sequence.

        Returns the raw dict unchanged if it is already at the current version.

        Raises MigrationPathNotFound if no registered path exists.

        """

        stored = raw.get("schema_version", "v1")

        if stored == self._current:

            return raw

        path = self._resolve_path(stored, self._current)

        data = dict(raw)

        for from_v, to_v in path:

            migration_fn = self._registry.get((from_v, to_v))

            if migration_fn is None:

                raise MigrationPathNotFound(

                    f"No migration registered for {from_v} -> {to_v}."

                )

            data = migration_fn(data)

            data["schema_version"] = to_v

        return data

    def _resolve_path(

        self, from_v: str, to_v: str

    ) -> list[tuple[str, str]]:

        """

        Resolves a linear path through registered version pairs.

        Assumes versions are named in a way that sorts correctly

        (v1, v2, v3 or YYYY-MM-DD format).

        """

        known_versions = sorted(

            {v for pair in self._registry for v in pair}

        )

        try:

            start = known_versions.index(from_v)

            end   = known_versions.index(to_v)

        except ValueError as exc:

            raise MigrationPathNotFound(str(exc)) from exc

        return [

            (known_versions[i], known_versions[i + 1])

            for i in range(start, end)

        ]

class MigrationPathNotFound(Exception):

    pass

# ---------------------------------------------------------------------------

# Example: migration from v1 to v2

# Scenario: ValidatingOrderState was renamed to OrderValidationState,

# and a new required field (escalation_count) was added to context_data.

# ---------------------------------------------------------------------------

def migrate_v1_to_v2(raw: dict) -> dict:

    data = dict(raw)

    # 1. Remap the renamed state in current_state.

    if data.get("current_state") == "validating_order":

        data["current_state"] = "order_validation"

    # 2. Remap any occurrences of the old state name in the history list.

    data["history"] = [

        "order_validation" if h == "validating_order" else h

        for h in data.get("history", [])

    ]

    # 3. Add the new required field with a safe default for old threads.

    context = dict(data.get("context_data") or {})

    context.setdefault("escalation_count", 0)

    data["context_data"] = context

    return data

# ---------------------------------------------------------------------------

# Integration into PostgresCheckpointStore.load()

# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION = "v2"

migrator = CheckpointMigrator(current_version=CURRENT_SCHEMA_VERSION)

migrator.register("v1", "v2", migrate_v1_to_v2)

# Inside PostgresCheckpointStore.load():

#

#   row = cur.fetchone()

#   raw = {

#       "schema_version":  row[0],

#       "current_state":   row[1],

#       "context_data":    row[2],

#       "history":         row[3],

#   }

#   raw = migrator.migrate(raw)   # <-- applied before any deserialization

#

# The migrated raw dict is then used to construct WorkflowContext

# exactly as before. The new schema_version is written to the database

# on the thread's next state transition through save().
