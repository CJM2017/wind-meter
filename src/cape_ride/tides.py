"""NOAA tide prediction client and deterministic phase classifier."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from cape_ride.config import SpotConfig
from cape_ride.errors import ProviderError, SchemaError
from cape_ride.http_client import JsonHttpClient, JsonObject, JsonValue
from cape_ride.models import TideExtreme, TidePeriod, TidePhase, TideState
from cape_ride.wind import ForecastRange

NOAA_ENDPOINT = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
LOCAL_TIMEZONE = ZoneInfo("America/New_York")
EXTREME_BUFFER = timedelta(hours=2)
NOAA_USER_AGENT = "cape-ride/0.1"


class TideClient:
    """Fetch public NOAA extrema and derive tide phases."""

    def __init__(self, http_client: JsonHttpClient) -> None:
        self._http_client = http_client

    def get_current(self, spot: SpotConfig, now: datetime | None = None) -> TideState:
        """Return the classified tide state at the requested instant."""
        local_now = _local_datetime(now or datetime.now(tz=LOCAL_TIMEZONE))
        extrema = self.get_extrema(
            spot,
            local_now - timedelta(days=1),
            local_now + timedelta(days=1),
        )
        return classify_tide(spot, local_now, extrema)

    def get_forecast_periods(
        self,
        spot: SpotConfig,
        forecast_range: ForecastRange,
    ) -> tuple[TidePeriod, ...]:
        """Return phase periods covering a wind forecast range."""
        extrema = self.get_extrema(
            spot,
            forecast_range.start - timedelta(days=1),
            forecast_range.end + timedelta(days=1),
        )
        boundaries = {forecast_range.start, forecast_range.end}
        for extreme in extrema:
            for boundary in (extreme.at - EXTREME_BUFFER, extreme.at + EXTREME_BUFFER):
                if forecast_range.start < boundary < forecast_range.end:
                    boundaries.add(boundary)
        ordered = sorted(boundaries)
        periods: list[TidePeriod] = []
        for start, end in zip(ordered, ordered[1:]):
            midpoint = start + (end - start) / 2
            phase = classify_tide(spot, midpoint, extrema).phase
            period = TidePeriod(
                spot=spot.key,
                station_id=spot.tide_station_id,
                phase=phase,
                start=start,
                end=end,
            )
            if periods and periods[-1].phase == period.phase and periods[-1].end == start:
                previous = periods[-1]
                periods[-1] = TidePeriod(
                    spot=previous.spot,
                    station_id=previous.station_id,
                    phase=previous.phase,
                    start=previous.start,
                    end=end,
                )
            else:
                periods.append(period)
        return tuple(periods)

    def get_extrema(
        self,
        spot: SpotConfig,
        start: datetime,
        end: datetime,
    ) -> tuple[TideExtreme, ...]:
        """Fetch NOAA high/low predictions for an inclusive local date range."""
        local_start = _local_datetime(start)
        local_end = _local_datetime(end)
        payload = self._http_client.get_json(
            NOAA_ENDPOINT,
            {
                "product": "predictions",
                "application": "cape-ride",
                "begin_date": local_start.strftime("%Y%m%d"),
                "end_date": local_end.strftime("%Y%m%d"),
                "datum": "MLLW",
                "station": spot.tide_station_id,
                "time_zone": "lst_ldt",
                "units": "english",
                "interval": "hilo",
                "format": "json",
            },
            {"User-Agent": NOAA_USER_AGENT, "Accept": "application/json"},
        )
        return _parse_extrema(payload, spot.tide_station_id)


def classify_tide(
    spot: SpotConfig,
    at: datetime,
    extrema: Iterable[TideExtreme],
) -> TideState:
    """Classify one instant using two-hour buffers around high and low tides."""
    local_at = _local_datetime(at)
    ordered = tuple(sorted(extrema, key=lambda extreme: extreme.at))
    if not ordered:
        raise ProviderError("NOAA returned no tide predictions")

    previous = next(
        (extreme for extreme in reversed(ordered) if extreme.at <= local_at),
        None,
    )
    following = next((extreme for extreme in ordered if extreme.at > local_at), None)
    nearby = min(ordered, key=lambda extreme: abs(extreme.at - local_at))
    if abs(nearby.at - local_at) <= EXTREME_BUFFER:
        phase = TidePhase.NEAR_HIGH if nearby.kind == "H" else TidePhase.NEAR_LOW
    elif previous is None or following is None:
        raise ProviderError("NOAA predictions do not bracket the requested time")
    elif previous.kind == "L" and following.kind == "H":
        phase = TidePhase.MID_RISING
    elif previous.kind == "H" and following.kind == "L":
        phase = TidePhase.MID_FALLING
    else:
        raise SchemaError("NOAA tide extrema do not alternate high and low")

    return TideState(
        spot=spot.key,
        station_id=spot.tide_station_id,
        station_name=spot.tide_station_name,
        at=local_at,
        phase=phase,
        previous_extreme=previous,
        next_extreme=following,
    )


def tide_state_from_period(
    spot: SpotConfig,
    at: datetime,
    periods: Iterable[TidePeriod],
) -> TideState:
    """Create a lightweight tide state from precomputed forecast periods."""
    local_at = _local_datetime(at)
    period = next(
        (item for item in periods if item.start <= local_at < item.end),
        None,
    )
    if period is None:
        raise ProviderError("Tide forecast does not cover the wind interval")
    return TideState(
        spot=spot.key,
        station_id=spot.tide_station_id,
        station_name=spot.tide_station_name,
        at=local_at,
        phase=period.phase,
        previous_extreme=None,
        next_extreme=None,
    )


def _parse_extrema(payload: JsonObject, station_id: str) -> tuple[TideExtreme, ...]:
    raw_error = payload.get("error")
    if isinstance(raw_error, dict):
        message = raw_error.get("message")
        detail = message if isinstance(message, str) else "unknown NOAA error"
        raise ProviderError(f"NOAA rejected request: {detail}")
    raw_predictions = payload.get("predictions")
    if not isinstance(raw_predictions, list):
        raise SchemaError("NOAA response is missing predictions")
    extrema: list[TideExtreme] = []
    for raw_prediction in raw_predictions:
        if not isinstance(raw_prediction, dict):
            raise SchemaError("NOAA predictions must contain objects")
        prediction = raw_prediction
        at = _parse_noaa_datetime(prediction.get("t"))
        height = _parse_float(prediction.get("v"))
        kind = _parse_kind(prediction.get("type"))
        extrema.append(
            TideExtreme(
                station_id=station_id,
                at=at,
                height_feet=height,
                kind=kind,
            )
        )
    if not extrema:
        raise ProviderError("NOAA returned no tide predictions")
    return tuple(sorted(extrema, key=lambda extreme: extreme.at))


def _parse_noaa_datetime(value: JsonValue | None) -> datetime:
    if not isinstance(value, str):
        raise SchemaError("NOAA prediction is missing time")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError as error:
        raise SchemaError("NOAA prediction has an invalid time") from error
    return parsed.replace(tzinfo=LOCAL_TIMEZONE)


def _parse_float(value: JsonValue | None) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
    raise SchemaError("NOAA prediction has an invalid height")


def _parse_kind(value: JsonValue | None) -> str:
    if value in ("H", "L"):
        return value
    raise SchemaError("NOAA prediction has an invalid tide type")


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(LOCAL_TIMEZONE)

