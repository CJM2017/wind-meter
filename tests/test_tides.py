from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from cape_ride.config import load_config
from cape_ride.models import TidePhase
from cape_ride.tides import TideClient, classify_tide
from cape_ride.wind import make_forecast_range
from tests.support import FakeHttpClient, fixture

LOCAL = ZoneInfo("America/New_York")


class TideClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spot = load_config().spots["wall"]

    def test_classifies_two_hour_boundaries_and_mid_tide(self) -> None:
        http = FakeHttpClient(fixture("tides.json"))
        client = TideClient(http)
        extrema = client.get_extrema(
            self.spot,
            datetime(2026, 8, 14, 0, 0, tzinfo=LOCAL),
            datetime(2026, 8, 15, 0, 0, tzinfo=LOCAL),
        )

        cases = (
            (datetime(2026, 8, 14, 8, 30, tzinfo=LOCAL), TidePhase.NEAR_LOW),
            (datetime(2026, 8, 14, 8, 31, tzinfo=LOCAL), TidePhase.MID_RISING),
            (datetime(2026, 8, 14, 10, 30, tzinfo=LOCAL), TidePhase.NEAR_HIGH),
            (datetime(2026, 8, 14, 14, 30, tzinfo=LOCAL), TidePhase.NEAR_HIGH),
            (datetime(2026, 8, 14, 14, 31, tzinfo=LOCAL), TidePhase.MID_FALLING),
        )
        for at, expected in cases:
            with self.subTest(at=at):
                self.assertEqual(expected, classify_tide(self.spot, at, extrema).phase)

    def test_forecast_periods_cover_requested_range(self) -> None:
        http = FakeHttpClient(fixture("tides.json"))
        client = TideClient(http)
        now = datetime(2026, 8, 14, 8, 31, tzinfo=LOCAL)
        forecast_range = make_forecast_range(now, 1)

        periods = client.get_forecast_periods(self.spot, forecast_range)

        self.assertEqual(forecast_range.start, periods[0].start)
        self.assertEqual(forecast_range.end, periods[-1].end)
        self.assertEqual(TidePhase.MID_RISING, periods[0].phase)
        self.assertIn(TidePhase.MID_FALLING, [period.phase for period in periods])
        params = http.requests[0][1]
        self.assertEqual("hilo", params["interval"])
        self.assertEqual("8447605", params["station"])


if __name__ == "__main__":
    unittest.main()
