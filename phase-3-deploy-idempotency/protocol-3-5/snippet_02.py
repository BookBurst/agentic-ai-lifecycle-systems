from __future__ import annotations

from typing import Any, Callable

class UnsupportedAgentVersion(Exception):

    pass

class VersionRouter:

    """

    Dispatches orchestration to the correct version handler based on

    the agent_version tag stored in the thread checkpoint.

    New threads always run under the current version.

    Existing threads always run under the version that created them.

    There is no automatic promotion of old threads to new handler logic.

    That decision belongs to the migration protocol, not to this router.

    """

    def __init__(

        self,

        handlers:        dict[str, Callable],

        current_version: str,

    ) -> None:

        if current_version not in handlers:

            raise ValueError(

                f"current_version '{current_version}' has no registered handler."

            )

        self._handlers = handlers

        self._current  = current_version

    def handle_new_thread(self, request: Any) -> Any:

        """

        All new thread creation goes through the current version handler.

        The agent_version written to the checkpoint at thread creation

        is always self._current.

        """

        return self._handlers[self._current](request)

    def handle_existing_thread(self, checkpoint: dict, event: Any) -> Any:

        """

        Reads the agent_version from the checkpoint and routes to the

        handler that created the thread. If the version is not registered,

        this raises immediately rather than defaulting to the current

        version -- defaulting would silently apply new logic to old state,

        which is exactly the failure this router exists to prevent.

        """

        version = checkpoint.get("agent_version", "v1")

        handler = self._handlers.get(version)

        if handler is None:

            raise UnsupportedAgentVersion(

                f"No handler registered for agent_version '{version}'. "

                f"This thread was created before a deprecation policy was "

                f"defined for this version. Freeze and escalate to human review."

            )

        return handler(checkpoint, event)

# ---------------------------------------------------------------------------

# Registration example: v1 and v2 running simultaneously

# ---------------------------------------------------------------------------

CURRENT_AGENT_VERSION = "v2"

router = VersionRouter(

    handlers={

        "v1": handle_v1_thread,   # the v1 orchestration function

        "v2": handle_v2_thread,   # the v2 orchestration function

    },

    current_version=CURRENT_AGENT_VERSION,

)
