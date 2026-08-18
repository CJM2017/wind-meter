"""Authenticated iKitesurf observation and Blend forecast client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from cape_ride.config import SpotConfig, WindCredentials
from cape_ride.errors import ProviderError, SchemaError
from cape_ride.http_client import JsonHttpClient, JsonObject, JsonValue
from cape_ride.models import DataStatus, WindForecast, WindForecastPoint, WindObservation

CURRENT_ENDPOINT = "https://api.weatherflow.com/wxengine/rest/spot/getSpotSetByList"
FORECAST_ENDPOINT = "https://api.weatherflow.com/wxengine/rest/model/getModelDataBySpot"
BLEND_MODEL_ID = "-1"
LOCAL_TIMEZONE = ZoneInfo("America/New_York")
STALE_AFTER = timedelta(minutes=15)


@dataclass(frozen=True)
class ForecastRange:
    """Local forecast range beginning at invocation time."""

    start: datetime
    end: datetime
    days: int


class WindClient:
    """Fetch and normalize current and forecast iKitesurf data."""

    def __init__(
        self,
        http_client: JsonHttpClient,
        credentials: WindCredentials,
    ) -> None:
        self._http_client = http_client
        self._credentials = credentials

    def get_current(
        self,
        spots: Iterable[SpotConfig],
        now: datetime | None = None,
    ) -> tuple[WindObservation, ...]:
        """Return one current result for every requested spot."""
        requested = tuple(spots)
        if not requested:
            return ()
        local_now = _local_datetime(now or datetime.now(tz=LOCAL_TIMEZONE))
        payload = self._http_client.get_json(
            CURRENT_ENDPOINT,
            self._current_params(requested),
            self._headers(),
        )
        _require_success(payload)
        rows = _tabular_rows(payload)
        by_spot_id = {
            spot_id: row
            for row in rows
            if (spot_id := _optional_int(row.get("spot_id"))) is not None
        }
        return tuple(
            _parse_observation(spot, by_spot_id.get(spot.provider_spot_id), local_now)
            for spot in requested
        )

    def get_forecast(
        self,
        spot: SpotConfig,
        days: int = 3,
        now: datetime | None = None,
    ) -> tuple[WindForecast, ForecastRange]:
        """Return un-interpolated Blend points in the requested local-day range."""
        local_now = _local_datetime(now or datetime.now(tz=LOCAL_TIMEZONE))
        forecast_range = make_forecast_range(local_now, days)
        payload = self._http_client.get_json(
            FORECAST_ENDPOINT,
            self._forecast_params(spot),
            self._headers(),
        )
        _require_success(payload)
        model_name = _required_string(payload.get("model_name"), "model_name")
        if "blend" not in model_name.lower():
            raise SchemaError("Forecast response is not the Blend model")
        parsed = _parse_forecast_rows(payload, spot, model_name)
        points = _with_intervals(parsed)
        selected = tuple(
            _cap_point(point, forecast_range.end)
            for point in points
            if forecast_range.start <= point.valid_at < forecast_range.end
        )
        return (
            WindForecast(
                spot=spot.key,
                provider_spot_id=spot.provider_spot_id,
                model_name=model_name,
                points=selected,
            ),
            forecast_range,
        )

    def _current_params(self, spots: tuple[SpotConfig, ...]) -> dict[str, str]:
        return {
            "wa_ver": "1777",
            "device_id": "00d8a1231a5807fd67e7d78d846664e1",
            "device_type": "iPhone",
            "device_os": "18.5",
            "wf_apikey": self._credentials.api_key,
            "wf_token": self._credentials.token,
            "activity": "Kite",
            "spot_list": ",".join(str(spot.provider_spot_id) for spot in spots),
            "fav_spot_list": "",
            "spot_types": "1,100,101",
            "include_spot_products": "false",
            "page": "1",
            "units_distance": "mi",
            "units_wind": "kts",
            "units_temp": "f",
            "sort": "distance",
            "num_per_page": "100",
            "v": "1.3",
            "format": "json",
        }

    def _forecast_params(self, spot: SpotConfig) -> dict[str, str]:
        return {
            "model_id": BLEND_MODEL_ID,
            "spot_id": str(spot.provider_spot_id),
            "units_wind": "kts",
            "units_temp": "f",
            "format": "json",
            "wf_apikey": self._credentials.api_key,
            "wf_token": self._credentials.token,
            "v": "1.3",
        }

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._credentials.user_agent or "iKitesurf/1777 CFNetwork/3826.500.131 Darwin/24.5.0",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }


def validate_days(days: int) -> int:
    """Validate the public 1 through 10 day forecast boundary."""
    if not 1 <= days <= 10:
        raise ValueError("days must be between 1 and 10")
    return days


def make_forecast_range(now: datetime, days: int) -> ForecastRange:
    """Create a range from now through the selected local calendar days."""
    validate_days(days)
    local_now = _local_datetime(now)
    first_midnight = datetime.combine(local_now.date(), time.min, tzinfo=LOCAL_TIMEZONE)
    return ForecastRange(
        start=local_now,
        end=first_midnight + timedelta(days=days),
        days=days,
    )


def _parse_observation(
    spot: SpotConfig,
    row: JsonObject | None,
    now: datetime,
) -> WindObservation:
    if row is None:
        return WindObservation(
            spot=spot.key,
            provider_spot_id=spot.provider_spot_id,
            provider_name=spot.provider_name,
            observed_at=None,
            average_knots=None,
            lull_knots=None,
            gust_knots=None,
            direction_degrees=None,
            direction_cardinal=None,
            age_seconds=None,
            status=DataStatus.UNAVAILABLE,
            status_message="Spot was absent from the provider response",
        )

    observed_at = _parse_provider_datetime(row.get("timestamp"))
    if observed_at is None:
        epoch = _optional_float(row.get("last_wind_ob_utc"))
        if epoch is not None:
            observed_at = datetime.fromtimestamp(epoch, tz=LOCAL_TIMEZONE)
    average = _optional_float(row.get("avg"))
    age_seconds = None
    status = DataStatus.UNAVAILABLE
    message = _optional_string(row.get("status_message"))
    if observed_at is not None:
        age_seconds = max(0, int((now - observed_at).total_seconds()))
    if average is None:
        message = message or "Current wind speed is unavailable"
    elif observed_at is None:
        message = message or "Observation timestamp is unavailable"
    elif now - observed_at > STALE_AFTER:
        status = DataStatus.STALE
        message = "Current wind reading is older than 15 minutes"
    else:
        status = DataStatus.AVAILABLE

    return WindObservation(
        spot=spot.key,
        provider_spot_id=spot.provider_spot_id,
        provider_name=_optional_string(row.get("name")) or spot.provider_name,
        observed_at=observed_at,
        average_knots=average,
        lull_knots=_optional_float(row.get("lull")),
        gust_knots=_optional_float(row.get("gust")),
        direction_degrees=_optional_int(row.get("dir")),
        direction_cardinal=_optional_string(row.get("dir_text")),
        age_seconds=age_seconds,
        status=status,
        status_message=message,
    )


def _parse_forecast_rows(
    payload: JsonObject,
    spot: SpotConfig,
    model_name: str,
) -> tuple[WindForecastPoint, ...]:
    raw_rows = payload.get("model_data")
    if not isinstance(raw_rows, list):
        raise SchemaError("Forecast response is missing model_data")
    points: list[WindForecastPoint] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise SchemaError("Forecast model_data must contain objects")
        row = raw_row
        valid_at = _parse_provider_datetime(row.get("model_time_local"))
        average = _optional_float(row.get("wind_speed"))
        direction = _optional_string(row.get("wind_dir_txt"))
        if valid_at is None or average is None or direction is None:
            continue
        points.append(
            WindForecastPoint(
                spot=spot.key,
                provider_spot_id=spot.provider_spot_id,
                model_name=model_name,
                valid_at=valid_at,
                valid_until=None,
                average_knots=average,
                gust_knots=_optional_float(row.get("wind_gust")),
                direction_degrees=_optional_int(row.get("wind_dir")),
                direction_cardinal=direction,
            )
        )
    if not points:
        raise SchemaError("Blend forecast contains no usable wind points")
    return tuple(sorted(points, key=lambda point: point.valid_at))


def _with_intervals(
    points: tuple[WindForecastPoint, ...],
) -> tuple[WindForecastPoint, ...]:
    return tuple(
        WindForecastPoint(
            spot=point.spot,
            provider_spot_id=point.provider_spot_id,
            model_name=point.model_name,
            valid_at=point.valid_at,
            valid_until=points[index + 1].valid_at if index + 1 < len(points) else None,
            average_knots=point.average_knots,
            gust_knots=point.gust_knots,
            direction_degrees=point.direction_degrees,
            direction_cardinal=point.direction_cardinal,
        )
        for index, point in enumerate(points)
    )


def _cap_point(point: WindForecastPoint, end: datetime) -> WindForecastPoint:
    valid_until = point.valid_until
    if valid_until is not None and valid_until > end:
        valid_until = end
    return WindForecastPoint(
        spot=point.spot,
        provider_spot_id=point.provider_spot_id,
        model_name=point.model_name,
        valid_at=point.valid_at,
        valid_until=valid_until,
        average_knots=point.average_knots,
        gust_knots=point.gust_knots,
        direction_degrees=point.direction_degrees,
        direction_cardinal=point.direction_cardinal,
    )


def _tabular_rows(payload: JsonObject) -> tuple[JsonObject, ...]:
    raw_names = payload.get("data_names")
    raw_values = payload.get("data_values")
    if not isinstance(raw_names, list) or not all(
        isinstance(name, str) for name in raw_names
    ):
        raise SchemaError("Current response is missing data_names")
    if not isinstance(raw_values, list):
        raise SchemaError("Current response is missing data_values")
    names = tuple(raw_names)
    rows: list[JsonObject] = []
    for raw_row in raw_values:
        if not isinstance(raw_row, list) or len(raw_row) != len(names):
            raise SchemaError("Current response row does not match data_names")
        rows.append(dict(zip(names, raw_row)))
    return tuple(rows)


def _require_success(payload: JsonObject) -> None:
    raw_status = payload.get("status")
    if not isinstance(raw_status, dict):
        raise SchemaError("Provider response is missing status")
    code = _optional_int(raw_status.get("status_code"))
    if code != 0:
        message = _optional_string(raw_status.get("status_message")) or "unknown error"
        raise ProviderError(f"Provider rejected request: {message}")


def _parse_provider_datetime(value: JsonValue | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, pattern).astimezone(LOCAL_TIMEZONE)
        except ValueError:
            continue
    return None


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(LOCAL_TIMEZONE)


def _required_string(value: JsonValue | None, name: str) -> str:
    parsed = _optional_string(value)
    if parsed is None:
        raise SchemaError(f"Provider response is missing {name}")
    return parsed


def _optional_string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: JsonValue | None) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _optional_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None

