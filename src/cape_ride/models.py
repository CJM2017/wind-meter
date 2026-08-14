"""Typed domain models shared by all three skills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DataStatus(StrEnum):
    """Availability of a provider value."""

    AVAILABLE = "available"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class TidePhase(StrEnum):
    """Deterministic phase derived from adjacent high and low tides."""

    NEAR_HIGH = "near_high"
    NEAR_LOW = "near_low"
    MID_RISING = "mid_rising"
    MID_FALLING = "mid_falling"


class RideResult(StrEnum):
    """Tri-state result used when required data may be unavailable."""

    RIDEABLE = "rideable"
    NOT_RIDEABLE = "not_rideable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class WindObservation:
    """Latest normalized reading for a configured wind meter."""

    spot: str
    provider_spot_id: int
    provider_name: str
    observed_at: datetime | None
    average_knots: float | None
    lull_knots: float | None
    gust_knots: float | None
    direction_degrees: int | None
    direction_cardinal: str | None
    age_seconds: int | None
    status: DataStatus
    status_message: str | None = None


@dataclass(frozen=True)
class WindForecastPoint:
    """One provider forecast interval with no interpolated values."""

    spot: str
    provider_spot_id: int
    model_name: str
    valid_at: datetime
    valid_until: datetime | None
    average_knots: float
    gust_knots: float | None
    direction_degrees: int | None
    direction_cardinal: str


@dataclass(frozen=True)
class WindForecast:
    """Forecast points for one configured spot."""

    spot: str
    provider_spot_id: int
    model_name: str
    points: tuple[WindForecastPoint, ...]


@dataclass(frozen=True)
class TideExtreme:
    """A NOAA predicted high or low tide."""

    station_id: str
    at: datetime
    height_feet: float
    kind: str


@dataclass(frozen=True)
class TideState:
    """Tide phase at a specific instant."""

    spot: str
    station_id: str
    station_name: str
    at: datetime
    phase: TidePhase
    previous_extreme: TideExtreme | None
    next_extreme: TideExtreme | None


@dataclass(frozen=True)
class TidePeriod:
    """A contiguous interval with one tide phase."""

    spot: str
    station_id: str
    phase: TidePhase
    start: datetime
    end: datetime


@dataclass(frozen=True)
class RideAssessment:
    """Current rideability result for one spot and discipline."""

    profile: str
    spot: str
    discipline: str
    result: RideResult
    preferred: bool | None
    reasons: tuple[str, ...]
    wind: WindObservation
    tide: TideState | None


@dataclass(frozen=True)
class RideWindow:
    """Contiguous forecast interval meeting one ride profile."""

    profile: str
    spot: str
    discipline: str
    start: datetime
    end: datetime
    minimum_average_knots: float
    maximum_average_knots: float
    directions: tuple[str, ...]
    tide_phases: tuple[TidePhase, ...]
    preferred: bool | None


@dataclass(frozen=True)
class RideForecast:
    """Rideable windows and status for one profile."""

    profile: str
    spot: str
    discipline: str
    result: RideResult
    reasons: tuple[str, ...]
    windows: tuple[RideWindow, ...]

