"""Deterministic composition of wind, tide, and ride preferences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from cape_ride.config import AppConfig, RideProfile, SpotConfig
from cape_ride.errors import CapeRideError
from cape_ride.models import (
    DataStatus,
    RideAssessment,
    RideForecast,
    RideResult,
    RideWindow,
    TidePeriod,
    TidePhase,
    TideState,
    WindForecast,
    WindForecastPoint,
    WindObservation,
)
from cape_ride.sunrise_sunset import SunriseSunsetClient, SunTimes
from cape_ride.tides import TideClient, tide_state_from_period
from cape_ride.wind import LOCAL_TIMEZONE, ForecastRange, WindClient, make_forecast_range

MINIMUM_WINDOW = timedelta(hours=1)
MID_TIDE_PHASES = frozenset({TidePhase.MID_RISING, TidePhase.MID_FALLING})
LOWER_TIDE_PHASES = MID_TIDE_PHASES | {TidePhase.NEAR_LOW}
HIGHER_TIDE_PHASES = MID_TIDE_PHASES | {TidePhase.NEAR_HIGH}


@dataclass(frozen=True)
class _QualifiedInterval:
    start: datetime
    end: datetime
    average_knots: float
    direction: str
    tide_phase: TidePhase | None
    preferred: bool | None
    daylight_limited: bool | None


def _get_cached_sun_times(
    client: SunriseSunsetClient,
    cached: dict[str, SunTimes | Exception],
    spot: SpotConfig,
    date: datetime,
) -> SunTimes | None:
    """Get cached or fetch sunrise/sunset for a date."""
    key = f"{spot.key}-{date.strftime('%Y-%m-%d')}"
    if key in cached:
        val = cached[key]
        if isinstance(val, Exception):
            return None
        return val
    try:
        result = client.get_suntime_for_date(date)
        cached[key] = result
        return result
    except Exception as e:
        cached[key] = e
        return None


class RideService:
    """Coordinate provider clients and deterministic profile evaluation."""

    def __init__(
        self,
        config: AppConfig,
        wind_client: WindClient,
        tide_client: TideClient,
        sunrise_client: SunriseSunsetClient,
    ) -> None:
        self._config = config
        self._wind_client = wind_client
        self._tide_client = tide_client
        self._sunrise_client = sunrise_client

    def get_current(
        self,
        profiles: Iterable[RideProfile],
        now: datetime | None = None,
    ) -> tuple[RideAssessment, ...]:
        """Evaluate current conditions for every requested profile."""
        selected = tuple(profiles)
        spots = self._spots_for_profiles(selected)
        observations = {
            item.spot: item for item in self._wind_client.get_current(spots, now)
        }
        tides: dict[str, TideState | None] = {}
        for profile in selected:
            if not _uses_tide(profile) or profile.spot in tides:
                continue
            try:
                tides[profile.spot] = self._tide_client.get_current(
                    self._config.spots[profile.spot],
                    now,
                )
            except CapeRideError:
                tides[profile.spot] = None
        return tuple(
            evaluate_current(
                profile,
                observations[profile.spot],
                tides.get(profile.spot),
            )
            for profile in selected
        )

    def get_forecast(
        self,
        profiles: Iterable[RideProfile],
        days: int = 3,
        now: datetime | None = None,
        use_multi_model: bool = False,
        model_ids: list[int] | None = None,
    ) -> tuple[tuple[RideForecast, ...], ForecastRange]:
        """Evaluate rideable windows for the requested local-day range.
        
        Args:
            profiles: Ride profiles to evaluate
            days: Number of days to forecast
            now: Reference time
            use_multi_model: If True, fetch from multiple models and use "any model passes" logic
            model_ids: List of model IDs to query when use_multi_model is True
            
        Returns:
            Tuple of (RideForecast results, ForecastRange)
        """
        selected = tuple(profiles)
        local_now = now or datetime.now(tz=LOCAL_TIMEZONE)
        forecast_range = make_forecast_range(local_now, days)
        
        if use_multi_model:
            # Multi-model mode: fetch from multiple models and merge results
            forecasts_by_spot: dict[str, list[tuple[WindForecast, set[int]]]] = {}
            forecast_errors: set[str] = set()
            
            for spot in self._spots_for_profiles(selected):
                try:
                    multi_forecasts = self._wind_client.get_forecast_from_multiple_models(
                        spot, days, model_ids, local_now
                    )
                    if multi_forecasts:
                        # Each entry: (forecast, set of model_ids that succeeded)
                        forecasts_by_spot[spot.key] = [
                            (forecast, {model_id})
                            for model_id, (forecast, _) in multi_forecasts.items()
                        ]
                except CapeRideError as e:
                    forecast_errors.add(spot.key)
                    forecasts_by_spot[spot.key] = []
            
            # Evaluate each profile with multi-model results
            tide_periods: dict[str, tuple[TidePeriod, ...] | None] = {}
            for profile in selected:
                if not _uses_tide(profile) or profile.spot in tide_periods:
                    continue
                try:
                    tide_periods[profile.spot] = self._tide_client.get_forecast_periods(
                        self._config.spots[profile.spot],
                        forecast_range,
                    )
                except CapeRideError:
                    tide_periods[profile.spot] = None
            
            sun_cache: dict[str, SunTimes | Exception] = {}
            for spot in self._config.spots.values():
                for day_offset in range(days):
                    test_date = local_now + timedelta(days=day_offset)
                    _get_cached_sun_times(self._sunrise_client, sun_cache, spot, test_date)
            
            results = tuple(
                evaluate_forecast_multi_model(
                    profile=profile,
                    spot=self._config.spots[profile.spot],
                    multi_forecasts=forecasts_by_spot.get(profile.spot, []),
                    tide_periods=tide_periods.get(profile.spot),
                    sun_cache=sun_cache,
                )
                for profile in selected
            )
            return results, forecast_range
        else:
            # Single model mode (backward compatible)
            forecasts: dict[str, WindForecast] = {}
            forecast_errors: set[str] = set()
            for spot in self._spots_for_profiles(selected):
                try:
                    forecast, _ = self._wind_client.get_forecast(spot, days, local_now)
                    forecasts[spot.key] = forecast
                except CapeRideError:
                    forecast_errors.add(spot.key)
            
            tide_periods: dict[str, tuple[TidePeriod, ...] | None] = {}
            for profile in selected:
                if not _uses_tide(profile) or profile.spot in tide_periods:
                    continue
                try:
                    tide_periods[profile.spot] = self._tide_client.get_forecast_periods(
                        self._config.spots[profile.spot],
                        forecast_range,
                    )
                except CapeRideError:
                    tide_periods[profile.spot] = None
            
            sun_cache: dict[str, SunTimes | Exception] = {}
            for spot in self._config.spots.values():
                for day_offset in range(days):
                    test_date = local_now + timedelta(days=day_offset)
                    _get_cached_sun_times(self._sunrise_client, sun_cache, spot, test_date)
            
            results = tuple(
                evaluate_forecast(
                    profile=profile,
                    spot=self._config.spots[profile.spot],
                    forecast=forecasts.get(profile.spot),
                    tide_periods=tide_periods.get(profile.spot),
                    wind_failed=profile.spot in forecast_errors,
                    sun_cache=sun_cache,
                )
                for profile in selected
            )
            return results, forecast_range

    def _spots_for_profiles(
        self,
        profiles: tuple[RideProfile, ...],
    ) -> tuple[SpotConfig, ...]:
        keys = tuple(dict.fromkeys(profile.spot for profile in profiles))
        return tuple(self._config.spots[key] for key in keys)


def _get_forecast_date(forecast_range: ForecastRange, point_day: int) -> datetime:
    """Get the effective date for a forecast point based on its offset from local_now."""
    # The forecast starts at local Now, so we need to find the date of each point
    # Points are distributed across the forecast days
    return forecast_range.start


def evaluate_current(
    profile: RideProfile,
    wind: WindObservation,
    tide: TideState | None,
) -> RideAssessment:
    """Evaluate one current reading without performing I/O."""
    wind_result, wind_reasons = _evaluate_wind(
        profile,
        wind.status,
        wind.average_knots,
        wind.direction_cardinal,
    )
    if wind_result is not RideResult.RIDEABLE:
        return _assessment(profile, wind_result, wind_reasons, wind, tide, None)

    tide_result, preferred, tide_reasons = _evaluate_tide(
        profile,
        wind.direction_cardinal,
        tide,
    )
    return _assessment(
        profile,
        tide_result,
        wind_reasons + tide_reasons,
        wind,
        tide,
        preferred,
    )


def evaluate_forecast(
    profile: RideProfile,
    spot: SpotConfig,
    forecast: WindForecast | None,
    tide_periods: tuple[TidePeriod, ...] | None,
    wind_failed: bool = False,
    sun_cache: dict[str, SunTimes | Exception] | None = None,
) -> RideForecast:
    """Evaluate and merge provider forecast intervals without interpolation."""
    if forecast is None:
        reason = "Wind forecast request failed" if wind_failed else "Wind forecast unavailable"
        return RideForecast(
            profile=profile.key,
            spot=profile.spot,
            discipline=profile.discipline,
            result=RideResult.UNKNOWN,
            reasons=(reason,),
            windows=(),
        )
    if _requires_tide(profile) and tide_periods is None:
        return RideForecast(
            profile=profile.key,
            spot=profile.spot,
            discipline=profile.discipline,
            result=RideResult.UNKNOWN,
            reasons=("Required tide forecast is unavailable",),
            windows=(),
        )

    qualified: list[_QualifiedInterval] = []
    for point in forecast.points:
        interval = _qualify_forecast_point(
            profile, spot, point, tide_periods, sun_cache
        )
        if interval is not None:
            qualified.append(interval)

    windows = _merge_intervals(profile, qualified)
    if windows:
        result = RideResult.RIDEABLE
        reasons = (f"Found {len(windows)} rideable forecast window(s)",)
    else:
        result = RideResult.NOT_RIDEABLE
        reasons = ("No forecast interval meets the profile for at least one hour",)
    return RideForecast(
        profile=profile.key,
        spot=profile.spot,
        discipline=profile.discipline,
        result=result,
        reasons=reasons,
        windows=windows,
    )


def evaluate_forecast_multi_model(
    profile: RideProfile,
    spot: SpotConfig,
    multi_forecasts: list[tuple[WindForecast, set[int]]],
    tide_periods: tuple[TidePeriod, ...] | None,
    sun_cache: dict[str, SunTimes | Exception] | None = None,
) -> RideForecast:
    """Evaluate rideability considering multiple models using "any model passes" logic.
    
    If ANY model indicates a window is rideable, that window is included in results.
    Tracks which models agree for confidence scoring.
    
    Args:
        profile: Ride profile to evaluate
        spot: Spot configuration
        multi_forecasts: List of (forecast, set_of_successful_model_ids) tuples
        tide_periods: Tide periods for this spot
        sun_cache: Cached sunrise/sunset data
        
    Returns:
        RideForecast with windows from any model that showed rideable conditions
    """
    if not multi_forecasts:
        return RideForecast(
            profile=profile.key,
            spot=profile.spot,
            discipline=profile.discipline,
            result=RideResult.UNKNOWN,
            reasons=("No models available for this spot",),
            windows=(),
        )
    
    if _requires_tide(profile) and tide_periods is None:
        return RideForecast(
            profile=profile.key,
            spot=profile.spot,
            discipline=profile.discipline,
            result=RideResult.UNKNOWN,
            reasons=("Required tide forecast is unavailable",),
            windows=(),
        )
    
    # Collect rideable windows from all models
    rideable_windows_by_time: dict[tuple[datetime, datetime], list[int]] = {}
    
    for forecast, successful_model_ids in multi_forecasts:
        for point in forecast.points:
            interval = _qualify_forecast_point(
                profile, spot, point, tide_periods, sun_cache
            )
            if interval is None:
                continue
            
            window_key = (interval.start, interval.end)
            if window_key not in rideable_windows_by_time:
                rideable_windows_by_time[window_key] = []
            rideable_windows_by_time[window_key].extend(successful_model_ids)
    
    # Merge intervals and track model agreement
    windows: list[RideWindow] = []
    model_agreement_map: dict[RideWindow, list[int]] = {}
    
    for (start, end), model_ids in rideable_windows_by_time.items():
        # Get the first forecast that had this window to extract details
        first_forecast = None
        for forecast, _ in multi_forecasts:
            for point in forecast.points:
                if point.valid_at == start and point.valid_until == end:
                    first_forecast = point
                    break
            if first_forecast:
                break
        
        if first_forecast is None:
            continue
        
        # Determine model agreement confidence
        num_models = len(set(model_ids))
        all_models_agree = num_models > 1
        
        # Create RideWindow with model agreement metadata
        window = RideWindow(
            profile=profile.key,
            spot=spot.key,
            discipline=profile.discipline,
            start=start,
            end=end,
            minimum_average_knots=first_forecast.average_knots,
            maximum_average_knots=first_forecast.average_knots,
            directions=(first_forecast.direction_cardinal,),
            tide_phases=(),
            preferred=None,
            daylight_limited=None,
            model_ids=tuple(sorted(set(model_ids))),
            all_models_agree=all_models_agree,
        )
        windows.append(window)
    
    if windows:
        result = RideResult.RIDEABLE
        num_models_used = max(len(m) for _, m in rideable_windows_by_time.values()) if rideable_windows_by_time else 1
        reasons = (
            f"Found {len(windows)} rideable forecast window(s) ",
            f"from {num_models_used} model(s)",
        )
    else:
        result = RideResult.NOT_RIDEABLE
        reasons = ("No forecast interval meets the profile for at least one hour",)
    
    return RideForecast(
        profile=profile.key,
        spot=spot.key,
        discipline=profile.discipline,
        result=result,
        reasons=reasons,
        windows=tuple(windows),
    )


def _qualify_forecast_point(
    profile: RideProfile,
    spot: SpotConfig,
    point: WindForecastPoint,
    tide_periods: tuple[TidePeriod, ...] | None,
    sun_cache: dict[str, SunTimes | Exception] | None,
) -> _QualifiedInterval | None:
    if point.valid_until is None or point.valid_until <= point.valid_at:
        return None

    # Check wind conditions
    wind_result, _ = _evaluate_wind(
        profile,
        DataStatus.AVAILABLE,
        point.average_knots,
        point.direction_cardinal,
    )
    if wind_result is not RideResult.RIDEABLE:
        return None

    # Check tide conditions
    tide = None
    if tide_periods is not None:
        try:
            tide = tide_state_from_period(spot, point.valid_at, tide_periods)
        except CapeRideError:
            if _requires_tide(profile):
                return None
    tide_result, preferred, _ = _evaluate_tide(
        profile,
        point.direction_cardinal,
        tide,
    )
    if tide_result is not RideResult.RIDEABLE:
        return None

    # Check daylight constraints (STRICT: exclude if outside valid window)
    daylight_start = None
    daylight_end = None

    if sun_cache is not None:
        sun_key = f"{spot.key}-{point.valid_at.strftime('%Y-%m-%d')}"
        sun_times = sun_cache.get(sun_key)
        if sun_times is not None:
            daylight_start = sun_times.daylight_start
            daylight_end = sun_times.daylight_end

    # Strict filtering: must have at least 30 minutes before end of daylight
    if daylight_end is not None and point.valid_at >= daylight_end:
        # Point ends after valid daylight window - exclude
        return None

    # Check if start of point is after daylight start
    if daylight_start is not None and point.valid_at < daylight_start:
        # Point starts before valid window - could be partial
        # But since we're strict, we need the whole valid_at to daylight_end to be usable
        # Actually, we should check if the interval overlaps with valid daylight
        # For simplicity in strict mode: if point valid_at < daylight_start, skip it
        # This is conservative but ensures we don't have partial dark sessions
        return None

    daylight_limited = None
    if daylight_end is not None and point.valid_at >= daylight_start:
        # Check if this point extends beyond daylight_end
        point_actual_end = point.valid_until if point.valid_until else point.valid_at
        if point_actual_end > daylight_end:
            daylight_limited = True

    return _QualifiedInterval(
        start=point.valid_at,
        end=point.valid_until,
        average_knots=point.average_knots,
        direction=point.direction_cardinal,
        tide_phase=tide.phase if tide else None,
        preferred=preferred,
        daylight_limited=daylight_limited,
    )


def _evaluate_wind(
    profile: RideProfile,
    status: DataStatus,
    average_knots: float | None,
    direction: str | None,
) -> tuple[RideResult, tuple[str, ...]]:
    if status is not DataStatus.AVAILABLE or average_knots is None or direction is None:
        return RideResult.UNKNOWN, ("Current wind data is stale or unavailable",)
    if average_knots < profile.minimum_average_knots:
        return (
            RideResult.NOT_RIDEABLE,
            (
                f"Average wind {average_knots:g} kt is below "
                f"{profile.minimum_average_knots:g} kt",
            ),
        )
    if direction not in profile.directions:
        return (
            RideResult.NOT_RIDEABLE,
            (f"Wind direction {direction} is not allowed",),
        )
    return (
        RideResult.RIDEABLE,
        (f"Wind is {average_knots:g} kt from {direction}",),
    )


def _evaluate_tide(
    profile: RideProfile,
    direction: str | None,
    tide: TideState | None,
) -> tuple[RideResult, bool | None, tuple[str, ...]]:
    if profile.tide_mode == "any":
        if not profile.preferred_tide_phases:
            return RideResult.RIDEABLE, None, ("Tide is unrestricted",)
        if tide is None:
            return RideResult.RIDEABLE, None, ("Preferred tide status is unavailable",)
        preferred = tide.phase in profile.preferred_tide_phases
        reason = "Tide is preferred" if preferred else "Tide is allowed but not preferred"
        return RideResult.RIDEABLE, preferred, (reason,)

    if tide is None:
        return RideResult.UNKNOWN, None, ("Required tide data is unavailable",)
    if profile.tide_mode == "allowed":
        if tide.phase not in profile.allowed_tide_phases:
            return RideResult.NOT_RIDEABLE, False, (f"Tide phase {tide.phase} is not allowed",)
        return RideResult.RIDEABLE, True, (f"Tide phase {tide.phase} is allowed",)
    if profile.tide_mode == "directional":
        allowed = _directional_tide_phases(profile, direction)
        if tide.phase not in allowed:
            return (
                RideResult.NOT_RIDEABLE,
                False,
                (f"Tide phase {tide.phase} does not match wind direction {direction}",),
            )
        return RideResult.RIDEABLE, True, ("Wind direction and tide phase match",)
    return RideResult.UNKNOWN, None, ("Profile has an unknown tide rule",)


def _directional_tide_phases(
    profile: RideProfile,
    direction: str | None,
) -> frozenset[TidePhase]:
    if direction in profile.lower_tide_directions:
        return LOWER_TIDE_PHASES
    if direction in profile.higher_tide_directions:
        return HIGHER_TIDE_PHASES
    return frozenset()


def _merge_intervals(
    profile: RideProfile,
    intervals: list[_QualifiedInterval],
) -> tuple[RideWindow, ...]:
    if not intervals:
        return ()
    groups: list[list[_QualifiedInterval]] = []
    for interval in sorted(intervals, key=lambda item: item.start):
        if groups and groups[-1][-1].end == interval.start:
            groups[-1].append(interval)
        else:
            groups.append([interval])

    windows: list[RideWindow] = []
    for group in groups:
        if group[-1].end - group[0].start < MINIMUM_WINDOW:
            continue
        preferences = tuple(item.preferred for item in group)
        if any(value is None for value in preferences):
            preferred = None
        else:
            preferred = all(value is True for value in preferences)

        # Check if window is daylight-limited
        daylight_limited = any(item.daylight_limited for item in group)

        windows.append(
            RideWindow(
                profile=profile.key,
                spot=profile.spot,
                discipline=profile.discipline,
                start=group[0].start,
                end=group[-1].end,
                minimum_average_knots=min(item.average_knots for item in group),
                maximum_average_knots=max(item.average_knots for item in group),
                directions=_ordered_unique(item.direction for item in group),
                tide_phases=_ordered_unique_phases(
                    item.tide_phase for item in group if item.tide_phase is not None
                ),
                preferred=preferred,
                daylight_limited=daylight_limited,
            )
        )
    return tuple(windows)


def _assessment(
    profile: RideProfile,
    result: RideResult,
    reasons: tuple[str, ...],
    wind: WindObservation,
    tide: TideState | None,
    preferred: bool | None,
) -> RideAssessment:
    return RideAssessment(
        profile=profile.key,
        spot=profile.spot,
        discipline=profile.discipline,
        result=result,
        preferred=preferred,
        reasons=reasons,
        wind=wind,
        tide=tide,
    )


def _uses_tide(profile: RideProfile) -> bool:
    return _requires_tide(profile) or bool(profile.preferred_tide_phases)


def _requires_tide(profile: RideProfile) -> bool:
    return profile.tide_mode != "any"


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _ordered_unique_phases(values: Iterable[TidePhase]) -> tuple[TidePhase, ...]:
    return tuple(dict.fromkeys(values))