import re

from dataclasses import dataclass, field

@dataclass

class MaskedPayload:

    sanitized_text: str

    token_map: dict[str, str] = field(default_factory=dict)

PII_PATTERNS = {

    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]?){13,16}\b"),

    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),

    "EMAIL": re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b"),

}

def scrub_before_egress(raw_text: str) -> MaskedPayload:

    """Deterministic, regex-driven masking layer. Runs before any

    network call leaves the perimeter. The LLM never sees raw PII."""

    sanitized = raw_text

    token_map: dict[str, str] = {}

    counter = 0

    for label, pattern in PII_PATTERNS.items():

        for match in pattern.finditer(sanitized):

            counter += 1

            placeholder = f"[{label}_{counter}]"

            token_map[placeholder] = match.group()

            sanitized = sanitized.replace(match.group(), placeholder, 1)

    return MaskedPayload(sanitized_text=sanitized, token_map=token_map)

def rehydrate_response(llm_output: str, token_map: dict[str, str]) -> str:

    """Reverses masking after the LLM call returns, restoring real

    values only inside your own infrastructure."""

    rehydrated = llm_output

    for placeholder, original_value in token_map.items():

        rehydrated = rehydrated.replace(placeholder, original_value)

    return rehydrated
