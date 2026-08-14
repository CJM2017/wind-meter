from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from cape_ride.errors import ProviderError
from cape_ride.http_client import RequestsJsonHttpClient


class HttpClientTests(unittest.TestCase):
    def test_transport_error_does_not_expose_url_or_query_secrets(self) -> None:
        underlying = requests.ConnectionError(
            "failed https://example.test?wf_token=secret-token"
        )
        with patch("cape_ride.http_client.requests.get", side_effect=underlying):
            with self.assertRaises(ProviderError) as raised:
                RequestsJsonHttpClient().get_json(
                    "https://example.test",
                    {"wf_token": "secret-token"},
                )

        message = str(raised.exception)
        self.assertEqual("Provider request failed", message)
        self.assertNotIn("secret-token", message)
        self.assertNotIn("example.test", message)

    def test_transient_transport_error_is_retried(self) -> None:
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"status":"ok"}'
        with patch(
            "cape_ride.http_client.requests.get",
            side_effect=[requests.ConnectionError("temporary"), response],
        ) as get:
            result = RequestsJsonHttpClient().get_json("https://example.test", {})

        self.assertEqual("ok", result["status"])
        self.assertEqual(2, get.call_count)


if __name__ == "__main__":
    unittest.main()
