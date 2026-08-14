from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from cape_ride.config import load_config
from cape_ride.evaluator import evaluate_current, evaluate_forecast
from cape_ride.models import (
    DataStatus,
    RideResult,
    TidePeriod,
    TidePhase,
    TideState,
    WindForecast,
    WindForecastPoint,
    WindObservation,
)

LOCAL = ZoneInfo("America/New_York")


class EvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.at = datetime(2026, 8, 14, 12, 0, tzinfo=LOCAL)

    def test_inclusive_wind_threshold(self) -> None:
        profile = self.config.profiles["wall:tt"]
        wind = self._wind("wall", 15.0, "SW")

        result = evaluate_current(profile, wind, None)

        self.assertEqual(RideResult.RIDEABLE, result.result)

    def test_disallowed_direction_is_not_rideable(self) -> None:
        profile = self.config.profiles["wall:tt"]
        wind = self._wind("wall", 20.0, "N")

        result = evaluate_current(profile, wind, None)

        self.assertEqual(RideResult.NOT_RIDEABLE, result.result)

    def test_wall_foil_tide_is_preference_only(self) -> None:
        profile = self.config.profiles["wall:foil"]
        wind = self._wind("wall", 12.0, "S")

        result = evaluate_current(profile, wind, None)

        self.assertEqual(RideResult.RIDEABLE, result.result)
        self.assertIsNone(result.preferred)

    def test_slick_direction_and_tide_are_hard_gate(self) -> None:
        profile = self.config.profiles["slick:tt"]
        wind = self._wind("slick", 15.0, "SW")
        near_high = self._tide("slick", TidePhase.NEAR_HIGH)
        near_low = self._tide("slick", TidePhase.NEAR_LOW)

        self.assertEqual(
            RideResult.NOT_RIDEABLE,
            evaluate_current(profile, wind, near_high).result,
        )
        self.assertEqual(
            RideResult.RIDEABLE,
            evaluate_current(profile, wind, near_low).result,
        )

    def test_flats_without_tide_is_unknown(self) -> None:
        profile = self.config.profiles["flats:tt"]

        result = evaluate_current(profile, self._wind("flats", 15.0, "N"), None)

        self.assertEqual(RideResult.UNKNOWN, result.result)

    def test_forecast_merges_only_adjacent_qualifying_intervals(self) -> None:
        profile = self.config.profiles["wall:tt"]
        spot = self.config.spots["wall"]
        points = (
            self._point("wall", 10, 11, 15.0, "SW"),
            self._point("wall", 11, 12, 16.0, "WSW"),
            self._point("wall", 13, 14, 17.0, "W"),
        )
        forecast = WindForecast("wall", 332, "Blend", points)

        result = evaluate_forecast(profile, spot, forecast, None)

        self.assertEqual(RideResult.RIDEABLE, result.result)
        self.assertEqual(2, len(result.windows))
        self.assertEqual(self.at.replace(hour=10), result.windows[0].start)
        self.assertEqual(self.at.replace(hour=12), result.windows[0].end)

    def test_hard_tide_forecast_failure_is_unknown(self) -> None:
        profile = self.config.profiles["flats:tt"]
        spot = self.config.spots["flats"]
        forecast = WindForecast(
            "flats",
            336,
            "Blend",
            (self._point("flats", 10, 11, 20.0, "N"),),
        )

        result = evaluate_forecast(profile, spot, forecast, None)

        self.assertEqual(RideResult.UNKNOWN, result.result)

    def test_flats_mid_tide_forecast_is_rideable(self) -> None:
        profile = self.config.profiles["flats:tt"]
        spot = self.config.spots["flats"]
        forecast = WindForecast(
            "flats",
            336,
            "Blend",
            (self._point("flats", 10, 11, 15.0, "N"),),
        )
        periods = (
            TidePeriod(
                spot="flats",
                station_id="8447241",
                phase=TidePhase.MID_RISING,
                start=self.at.replace(hour=9),
                end=self.at.replace(hour=12),
            ),
        )

        result = evaluate_forecast(profile, spot, forecast, periods)

        self.assertEqual(RideResult.RIDEABLE, result.result)
        self.assertEqual(1, len(result.windows))

    def _wind(self, spot: str, speed: float, direction: str) -> WindObservation:
        return WindObservation(
            spot=spot,
            provider_spot_id=self.config.spots[spot].provider_spot_id,
            provider_name=self.config.spots[spot].provider_name,
            observed_at=self.at,
            average_knots=speed,
            lull_knots=None,
            gust_knots=None,
            direction_degrees=None,
            direction_cardinal=direction,
            age_seconds=0,
            status=DataStatus.AVAILABLE,
        )

    def _tide(self, spot: str, phase: TidePhase) -> TideState:
        config = self.config.spots[spot]
        return TideState(
            spot=spot,
            station_id=config.tide_station_id,
            station_name=config.tide_station_name,
            at=self.at,
            phase=phase,
            previous_extreme=None,
            next_extreme=None,
        )

    def _point(
        self,
        spot: str,
        start_hour: int,
        end_hour: int,
        speed: float,
        direction: str,
    ) -> WindForecastPoint:
        return WindForecastPoint(
            spot=spot,
            provider_spot_id=self.config.spots[spot].provider_spot_id,
            model_name="Blend",
            valid_at=self.at.replace(hour=start_hour),
            valid_until=self.at.replace(hour=end_hour),
            average_knots=speed,
            gust_knots=None,
            direction_degrees=None,
            direction_cardinal=direction,
        )


if __name__ == "__main__":
    unittest.main()
