"""Small injectable JSON HTTP boundary."""

from __future__ import annotations

import json
import ssl
from typing import Protocol, TypeAlias, cast

import requests

from cape_ride.errors import ProviderError, SchemaError

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class JsonHttpClient(Protocol):
    """Transport contract used by provider clients and test fakes."""

    def get_json(
        self,
        base_url: str,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> JsonObject:
        """Return one decoded JSON object."""


class RequestsJsonHttpClient:
    """Requests-based JSON client that never includes request URLs in errors."""

    def __init__(self, timeout_seconds: float = 30.0, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._ca_bundle: str | bool = ssl.get_default_verify_paths().cafile or True

    def get_json(
        self,
        base_url: str,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> JsonObject:
        """Fetch and decode JSON with redacted failure messages."""
        response = self._get_with_retries(base_url, params, headers)
        try:
            decoded = json.loads(response.text)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise SchemaError("Provider returned invalid JSON") from error

        if not isinstance(decoded, dict) or not all(
            isinstance(key, str) for key in decoded
        ):
            raise SchemaError("Provider JSON root must be an object")
        return cast(JsonObject, decoded)

    def _get_with_retries(
        self,
        base_url: str,
        params: dict[str, str],
        headers: dict[str, str] | None,
    ) -> requests.Response:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = requests.get(
                    base_url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout_seconds,
                    verify=self._ca_bundle,
                )
                if response.status_code >= 500 and attempt < self._max_attempts:
                    continue
                response.raise_for_status()
                return response
            except requests.HTTPError as error:
                status_code = (
                    error.response.status_code if error.response is not None else "error"
                )
                raise ProviderError(f"Provider returned HTTP {status_code}") from error
            except requests.RequestException as error:
                if attempt == self._max_attempts:
                    raise ProviderError("Provider request failed") from error
        raise ProviderError("Provider request failed")
