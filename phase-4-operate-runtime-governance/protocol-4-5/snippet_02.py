import redis.sentinel

# Redis Sentinel configuration for the kill switch store.

# All reads go to the master. There is no replica read path

# for revocation status checks.

sentinel = redis.sentinel.Sentinel(

    sentinels=[

        ("sentinel-1.internal", 26379),

        ("sentinel-2.internal", 26379),

        ("sentinel-3.internal", 26379),

    ],

    socket_timeout=0.5,

    socket_connect_timeout=0.5,

)

# master() returns a client connected to the current master.

# If the master fails and a replica is promoted, the next call

# to master() connects to the new master automatically.

# There is no get_slave() or replica read path in this layer.

kill_switch_client = sentinel.master_for(

    "kill-switch",

    socket_timeout=0.5,

    decode_responses=True,

)

class KillSwitchStore:

    """

    Reads and writes agent revocation status through Redis Sentinel,

    always targeting the current master for both reads and writes.

    The absence of a replica read path is intentional and documented:

    stale revocation reads are a security failure, not a performance

    tradeoff. If the master is unreachable, reads raise KillSwitchUnavailable

    rather than falling back to a replica that may carry stale data.

    """

    REVOKED  = "revoked"

    ALIVE    = "alive"

    def __init__(self, client: redis.Redis) -> None:

        self._client = client

    def is_alive(self, agent_id: str) -> bool:

        """

        Returns True only if the agent's status is explicitly ALIVE.

        Any other result -- REVOKED, missing key, or connection error --

        defaults to False. An agent with an unresolvable status does not

        get to call tools.

        """

        try:

            status = self._client.get(f"agent:{agent_id}:status")

            return status == self.ALIVE

        except redis.RedisError as exc:

            raise KillSwitchUnavailable(

                f"Kill switch store unreachable for agent '{agent_id}': {exc}"

            )

    def revoke(self, agent_id: str, ttl_seconds: int = 86_400) -> None:

        """

        Marks an agent as revoked. The write uses WAIT to ensure at least

        one replica acknowledges the write before returning, providing a

        synchronous replication guarantee for this specific operation.

        """

        key = f"agent:{agent_id}:status"

        pipe = self._client.pipeline(transaction=True)

        pipe.set(key, self.REVOKED, ex=ttl_seconds)

        pipe.execute()

        # Ensure at least one replica received the write.

        self._client.execute_command("WAIT", 1, 500)

class KillSwitchUnavailable(Exception):

    pass
