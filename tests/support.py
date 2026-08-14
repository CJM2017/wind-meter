"""Shared offline test helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from cape_ride.http_client import JsonObject

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


class FakeHttpClient:
    """Return queued JSON objects without network access."""

    def __init__(self, *responses: JsonObject) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, dict[str, str], dict[str, str] | None]] = []

    def get_json(
        self,
        base_url: str,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> JsonObject:
        self.requests.append((base_url, params, headers))
        if not self.responses:
            raise AssertionError("Fake HTTP response queue is empty")
        return self.responses.pop(0)


def fixture(name: str) -> JsonObject:
    """Load one redacted JSON fixture."""
    decoded = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise AssertionError("Fixture root must be an object")
    return cast(JsonObject, decoded)

