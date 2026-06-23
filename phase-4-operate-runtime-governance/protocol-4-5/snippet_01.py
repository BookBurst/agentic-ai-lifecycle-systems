import psycopg2

from psycopg2 import OperationalError

import time

import logging

logger = logging.getLogger(__name__)

class ResilientCheckpointConnection:

    """

    Wraps psycopg2 with retry logic for transient connection failures

    during failover events. The connection string points to a managed

    endpoint (cloud provider or PgBouncer), not a raw primary IP.

    During a failover, connections will fail for a short window while

    the replica is being promoted. The retry loop here covers that window

    rather than surfacing an error to the caller immediately.

    max_retries and retry_delay should be calibrated against your

    provider's observed promotion latency. AWS RDS Multi-AZ promotion

    typically completes in 60-120 seconds; Google Cloud SQL HA is

    similar. Set max_retries * retry_delay to cover that window.

    """

    def __init__(

        self,

        dsn:         str,

        max_retries: int   = 8,

        retry_delay: float = 15.0,

    ) -> None:

        self._dsn         = dsn

        self._max_retries = max_retries

        self._retry_delay = retry_delay

    def connect(self) -> psycopg2.extensions.connection:

        last_error = None

        for attempt in range(1, self._max_retries + 1):

            try:

                conn = psycopg2.connect(self._dsn)

                if attempt > 1:

                    logger.info(

                        "checkpoint_store_reconnected",

                        extra={"attempts": attempt},

                    )

                return conn

            except OperationalError as exc:

                last_error = exc

                logger.warning(

                    "checkpoint_store_connection_failed",

                    extra={

                        "attempt": attempt,

                        "max_retries": self._max_retries,

                        "error": str(exc),

                    },

                )

                if attempt < self._max_retries:

                    time.sleep(self._retry_delay)

        raise CheckpointStoreUnavailable(

            f"Could not connect to checkpoint store after "

            f"{self._max_retries} attempts. Last error: {last_error}"

        )

class CheckpointStoreUnavailable(Exception):

    pass
