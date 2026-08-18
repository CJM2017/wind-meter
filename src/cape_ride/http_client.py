"""Small injectable JSON HTTP boundary."""

from __future__ import annotations

import json
import ssl
from typing import Protocol, cast, Union, Dict, Any, List, Optional
try:
    from typing import TypeAlias
except ImportError:
    from typing import NewType
    TypeAlias = lambda x: x  # type: ignore

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

from cape_ride.errors import ProviderError, SchemaError

JsonScalar = Union[str, int, float, bool, None]
JsonValue = Union[JsonScalar, List["JsonValue"], Dict[str, "JsonValue"]]
JsonObject = Dict[str, JsonValue]


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
    """Transport-agnostic JSON client with fallback to urllib."""

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
        if HAS_REQUESTS:
            return self._get_json_with_requests(base_url, params, headers)
        return self._get_json_with_urllib(base_url, params, headers)

    def _get_json_with_requests(
        self,
        base_url: str,
        params: dict[str, str],
        headers: dict[str, str] | None,
    ) -> JsonObject:
        """Use requests library if available."""
        response = self._get_with_retries_requests(base_url, params, headers)
        try:
            decoded = json.loads(response.text)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise SchemaError("Provider returned invalid JSON") from error

        if not isinstance(decoded, dict) or not all(
            isinstance(key, str) for key in decoded
        ):
            raise SchemaError("Provider JSON root must be an object")
        return cast(JsonObject, decoded)

    def _get_with_retries_requests(
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

    def _get_json_with_urllib(
        self,
        base_url: str,
        params: dict[str, str],
        headers: dict[str, str] | None,
    ) -> JsonObject:
        """Fallback to urllib if requests not available."""
        from urllib.parse import urlencode
        
        url = base_url
        if params:
            url = f"{url}?{urlencode(params)}"
            
        req = urllib.request.Request(url)
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
                
        for attempt in range(1, self._max_attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout_seconds) as response:
                    data = response.read().decode('utf-8')
                    try:
                        decoded = json.loads(data)
                    except (json.JSONDecodeError, UnicodeDecodeError) as error:
                        raise SchemaError("Provider returned invalid JSON") from error

                    if not isinstance(decoded, dict) or not all(
                        isinstance(key, str) for key in decoded
                    ):
                        raise SchemaError("Provider JSON root must be an object")
                    return cast(JsonObject, decoded)
                    
            except urllib.error.HTTPError as error:
                status_code = error.code
                raise ProviderError(f"Provider returned HTTP {status_code}") from error
            except urllib.error.URLError as error:
                if attempt == self._max_attempts:
                    raise ProviderError(f"Provider request failed: {error.reason}") from error
        raise ProviderError("Provider request failed")
