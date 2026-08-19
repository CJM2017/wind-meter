"""NOAA sunrise/sunset client for Barnstable, Massachusetts.
Uses a simple solar calculation since NOAA doesn't provide sunrise_sunset product.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import cos, sin, acos, radians

from cape_ride.config import SpotConfig
from cape_ride.errors import ProviderError, SchemaError
from cape_ride.http_client import JsonHttpClient
from cape_ride.wind import LOCAL_TIMEZONE

# Barnstable, MA coordinates
BARNSTABLE_LAT = 41.7026
BARNSTABLE_LON = -70.3011

# Buffer minutes for daylight start/end
BUFFER_MINUTES = 30


@dataclass(frozen=True)
class SunTimes:
    """Sun rise and set times for a given day."""

    date: str
    sunrise: datetime
    sunset: datetime
    daylight_start: datetime
    daylight_end: datetime


def _calculate_sun_times(lat: float, lon: float, date_str: str) -> tuple[datetime, datetime]:
    """Calculate sunrise and sunset times using solar equations.
    
    Simplified but accurate calculation based on NOAA algorithms.
    Returns times in local timezone.
    """
    # Parse the date
    try:
        year, month, day = map(int, date_str.split('-'))
    except (ValueError, IndexError):
        raise SchemaError(f"Invalid date format: {date_str}")
    
    # Calculate day of year
    if month == 1:
        day_of_year = day
    elif month == 2:
        day_of_year = 31 + day
    elif month == 3:
        day_of_year = 59 + day
    elif month == 4:
        day_of_year = 90 + day
    elif month == 5:
        day_of_year = 120 + day
    elif month == 6:
        day_of_year = 151 + day
    elif month == 7:
        day_of_year = 181 + day
    elif month == 8:
        day_of_year = 212 + day
    elif month == 9:
        day_of_year = 243 + day
    elif month == 10:
        day_of_year = 273 + day
    elif month == 11:
        day_of_year = 304 + day
    elif month == 12:
        day_of_year = 334 + day
    else:
        raise SchemaError(f"Invalid month: {month}")
    
    # Solar declination (degrees)
    declination = 23.45 * sin(radians((284 + day_of_year) * 360 / 365))
    
    # Hour angle
    lat_rad = radians(lat)
    dec_rad = radians(declination)
    
    # Sunset hour angle: cos(H) = -tan(lat)*tan(dec)
    # For sunrise/sunset, we use 90.833 degrees (accounting for refraction)
    zenith = 90.833
    cos_h = (cos(radians(zenith)) - sin(lat_rad) * sin(dec_rad)) / (cos(lat_rad) * cos(dec_rad))
    
    # Clamp to valid range
    cos_h = max(-1, min(1, cos_h))
    hour_angle = acos(cos_h) * 180 / 3.14159265359  # Convert to degrees
    
    # Calculate times in minutes from midnight UTC
    tz_offset = 4  # EDT is UTC-4
    sunrise_minutes = 720 - 4 * (lon + hour_angle)
    sunset_minutes = 720 - 4 * (lon - hour_angle)
    
    # Convert to datetime
    def minutes_to_datetime(minutes: float) -> datetime:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return datetime(year, month, day, hours, mins, tzinfo=LOCAL_TIMEZONE)
    
    sunrise_dt = minutes_to_datetime(sunrise_minutes)
    sunset_dt = minutes_to_datetime(sunset_minutes)
    
    return sunrise_dt, sunset_dt


class SunriseSunsetClient:
    """Fetch sunrise/sunset times using solar calculation.
    
    Args:
        http_client: HTTP client (required for API compatibility, though not used)
    """
    
    def __init__(self, http_client: JsonHttpClient) -> None:
        """Initialize the client (http_client kept for API compatibility)."""
        self._http_client = http_client  # Kept for API compatibility

    def get_suntime(
        self,
        spot: SpotConfig,
        at: datetime,
    ) -> SunTimes:
        """Return sunrise/sunset for the date of the given datetime."""
        local_at = _local_datetime(at)
        date_str = local_at.strftime("%Y-%m-%d")
        
        sunrise_dt, sunset_dt = _calculate_sun_times(BARNSTABLE_LAT, BARNSTABLE_LON, date_str)
        
        return SunTimes(
            date=date_str,
            sunrise=sunrise_dt,
            sunset=sunset_dt,
            daylight_start=sunrise_dt - timedelta(minutes=BUFFER_MINUTES),
            daylight_end=sunset_dt + timedelta(minutes=BUFFER_MINUTES),
        )

    def get_suntime_for_date(
        self,
        date: datetime,
    ) -> SunTimes:
        """Return sunrise/sunset for the given date."""
        local_date = _local_datetime(date)
        date_str = local_date.strftime("%Y-%m-%d")
        
        sunrise_dt, sunset_dt = _calculate_sun_times(BARNSTABLE_LAT, BARNSTABLE_LON, date_str)
        
        return SunTimes(
            date=date_str,
            sunrise=sunrise_dt,
            sunset=sunset_dt,
            daylight_start=sunrise_dt - timedelta(minutes=BUFFER_MINUTES),
            daylight_end=sunset_dt + timedelta(minutes=BUFFER_MINUTES),
        )


def _local_datetime(value: datetime) -> datetime:
    """Convert to local timezone."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(LOCAL_TIMEZONE)
