from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from cape_ride.config import WindCredentials, load_config
from cape_ride.errors import ProviderError, SchemaError
from cape_ride.models import DataStatus
from cape_ride.wind import WindClient, make_forecast_range, validate_days
from tests.support import FakeHttpClient, fixture

LOCAL = ZoneInfo("America/New_York")


class WindClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.credentials = WindCredentials("key", "token", "iKitesurf/test")

    def test_current_maps_reordered_rows_by_provider_spot_id(self) -> None:
        http = FakeHttpClient(fixture("current.json"))
        client = WindClient(http, self.credentials)
        now = datetime(2026, 8, 14, 12, 0, tzinfo=LOCAL)

        results = client.get_current(
            (self.config.spots["wall"], self.config.spots["pond"]),
            now,
        )

        self.assertEqual("wall", results[0].spot)
        self.assertEqual(16.0, results[0].average_knots)
        self.assertEqual(DataStatus.STALE, results[0].status)
        self.assertEqual("pond", results[1].spot)
        self.assertEqual(15.0, results[1].average_knots)
        self.assertEqual(DataStatus.AVAILABLE, results[1].status)
        request_params = http.requests[0][1]
        self.assertNotIn("device_id", request_params)
        self.assertEqual("key", request_params["wf_apikey"])

    def test_current_marks_missing_speed_unavailable(self) -> None:
        client = WindClient(FakeHttpClient(fixture("current.json")), self.credentials)
        now = datetime(2026, 8, 14, 12, 0, tzinfo=LOCAL)

        result = client.get_current((self.config.spots["slick"],), now)[0]

        self.assertEqual(DataStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.average_knots)

    def test_forecast_preserves_provider_cadence_and_filters_current_day(self) -> None:
        client = WindClient(FakeHttpClient(fixture("forecast.json")), self.credentials)
        now = datetime(2026, 8, 14, 12, 30, tzinfo=LOCAL)

        forecast, forecast_range = client.get_forecast(
            self.config.spots["wall"],
            days=1,
            now=now,
        )

        self.assertEqual(now, forecast_range.start)
        self.assertEqual(datetime(2026, 8, 15, 0, 0, tzinfo=LOCAL), forecast_range.end)
        self.assertEqual([13, 14, 17], [point.valid_at.hour for point in forecast.points])
        interval = forecast.points[1].valid_until - forecast.points[1].valid_at
        self.assertEqual(3, int(interval.total_seconds() / 3600))
        self.assertEqual(forecast_range.end, forecast.points[-1].valid_until)

    def test_days_boundary(self) -> None:
        now = datetime(2026, 8, 14, 9, 0, tzinfo=LOCAL)

        self.assertEqual(1, validate_days(1))
        self.assertEqual(10, validate_days(10))
        self.assertEqual(
            datetime(2026, 8, 24, 0, 0, tzinfo=LOCAL),
            make_forecast_range(now, 10).end,
        )
        for invalid in (0, 11):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_days(invalid)

    def test_forecast_range_uses_local_calendar_days_across_dst(self) -> None:
        now = datetime(2026, 10, 31, 12, 0, tzinfo=LOCAL)

        forecast_range = make_forecast_range(now, 3)

        self.assertEqual(datetime(2026, 11, 3, 0, 0, tzinfo=LOCAL), forecast_range.end)
        self.assertEqual(-5 * 3600, int(forecast_range.end.utcoffset().total_seconds()))

    def test_provider_status_error_is_explicit(self) -> None:
        payload = {"status": {"status_code": 2, "status_message": "Denied"}}
        client = WindClient(FakeHttpClient(payload), self.credentials)

        with self.assertRaisesRegex(ProviderError, "Denied"):
            client.get_current((self.config.spots["wall"],))

    def test_tabular_schema_drift_is_rejected(self) -> None:
        payload = {
            "status": {"status_code": 0, "status_message": "Success"},
            "data_names": ["spot_id", "avg"],
            "data_values": [[332]],
        }
        client = WindClient(FakeHttpClient(payload), self.credentials)

        with self.assertRaises(SchemaError):
            client.get_current((self.config.spots["wall"],))


if __name__ == "__main__":
    unittest.main()
