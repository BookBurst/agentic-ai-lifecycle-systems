import hashlib

import time

from dataclasses import dataclass

from typing import Optional

import requests

def generate_idempotency_key(thread_id: str, action_name: str, sequence: int) -> str:

    """

    Builds a key from data that stays fixed across every retry of the

    SAME logical action. Never use uuid4() or any timestamp here. A

    random or time-based value defeats the entire point: it would make

    a retry indistinguishable from a brand new request.

    `sequence` is the action's position in the thread's history, taken

    from the same checkpoint store used in Protocol 2.4. It only

    advances when the workflow moves to a genuinely different action,

    never when an action is simply being retried.

    """

    raw = f"{thread_id}:{action_name}:{sequence}"

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@dataclass

class ChargeResult:

    success: bool

    charge_id: Optional[str]

    idempotency_key: str

class PaymentGateway:

    """Wraps an external payment API and guarantees that every attempt

    at the same logical charge, including retries after a dropped

    connection, carries the identical idempotency key."""

    def __init__(self, api_base: str, max_retries: int = 3):

        self.api_base = api_base

        self.max_retries = max_retries

    def charge_customer(

        self, thread_id: str, sequence: int, amount_cents: int, customer_id: str

    ) -> ChargeResult:

        idempotency_key = generate_idempotency_key(thread_id, "charge_customer", sequence)

        for attempt in range(1, self.max_retries + 1):

            try:

                response = requests.post(

                    f"{self.api_base}/charges",

                    headers={"Idempotency-Key": idempotency_key},

                    json={"amount": amount_cents, "customer_id": customer_id},

                    timeout=5,

                )

                response.raise_for_status()

                payload = response.json()

                return ChargeResult(

                    success=True,

                    charge_id=payload["charge_id"],

                    idempotency_key=idempotency_key,

                )

            except requests.exceptions.RequestException:

                # A timeout or dropped connection here does not tell us

                # whether the gateway processed the charge before it

                # happened. Retrying is safe precisely because the key

                # never changes between attempts.

                time.sleep(2 ** attempt)

                continue

        raise RuntimeError(

            f"Charge failed after {self.max_retries} attempts. "

            f"Idempotency key {idempotency_key} preserved for manual reconciliation."

        )
