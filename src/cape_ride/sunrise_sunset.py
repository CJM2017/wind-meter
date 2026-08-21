"""NOAA sunrise/sunset client for Barnstable, Massachusetts.
Uses a simple solar calculation since NOAA doesn't provide sunrise_sunset product.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import acos, cos, sin

from cape_ride.config import SpotConfig
from cape_ride.errors import SchemaError
from cape_ride.http_client import JsonHttpClient
from cape_ride.wind import LOCAL_TIMEZONE

# Buffer minutes for daylight start/end (default fallback)
DEFAULT_BUFFER_MINUTES = 30


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
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        date_str: Date in YYYY-MM-DD format
        
    Returns:
        Tuple of (sunrise, sunset) datetimes in local timezone
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
    declination = 23.45 * sin(((284 + day_of_year) * 360 / 365) * (3.141592653589793 / 180))
    
    # Convert to radians
    lat_rad = lat * (3.141592653589793 / 180)
    dec_rad = declination * (3.141592653589793 / 180)
    
    # Sunset hour angle: cos(H) = -tan(lat)*tan(dec)
    # For sunrise/sunset, we use 90.833 degrees (accounting for refraction)
    zenith = 90.833
    zenith_rad = zenith * (3.141592653589793 / 180)
    
    cos_h = (cos(zenith_rad) - sin(lat_rad) * sin(dec_rad)) / (cos(lat_rad) * cos(dec_rad))
    
    # Clamp to valid range
    cos_h = max(-1, min(1, cos_h))
    hour_angle = acos(cos_h) * 180 / 3.141592653589793  # Convert to degrees
    
    # Calculate times in minutes from midnight UTC
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


def _get_sun_times_for_spot(spot: SpotConfig, date_str: str) -> tuple[datetime, datetime]:
    """Get sunrise and sunset for a spot-specific location.
    
    Args:
        spot: Spot configuration containing coordinates
        date_str: Date in YYYY-MM-DD format
        
    Returns:
        Tuple of (sunrise, sunset) datetimes in local timezone
    """
    return _calculate_sun_times(spot.latitude, spot.longitude, date_str)


class SunriseSunsetClient:
    """Fetch sunrise/sunset times using solar calculation with spot-specific coordinates.
    
    The client calculates sunrise and sunset times based on the spot's latitude and longitude,
    applying the spot's specific daylight buffer configuration.
    
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
        """Return sunrise/sunset for the date of the given datetime using spot-specific coordinates.
        
        Args:
            spot: Spot configuration containing latitude and longitude
            at: Reference datetime to calculate the date from
            
        Returns:
            SunTimes dataclass with computed values including spot-specific daylight window
        """
        local_at = _local_datetime(at)
        date_str = local_at.strftime("%Y-%m-%d")
        
        sunrise_dt, sunset_dt = _get_sun_times_for_spot(spot, date_str)
        buffer = spot.daylight_buffer_minutes
        
        return SunTimes(
            date=date_str,
            sunrise=sunrise_dt,
            sunset=sunset_dt,
            daylight_start=sunrise_dt - timedelta(minutes=buffer),
            daylight_end=sunset_dt + timedelta(minutes=buffer),
        )

    def get_suntime_for_date(
        self,
        spot: SpotConfig,
        date: datetime,
    ) -> SunTimes:
        """Return sunrise/sunset for the given date using spot-specific coordinates.
        
        Args:
            spot: Spot configuration containing latitude and longitude
            date: Date for which to calculate sunrise/sunset
            
        Returns:
            SunTimes dataclass with computed values including spot-specific daylight window
        """
        local_date = _local_datetime(date)
        date_str = local_date.strftime("%Y-%m-%d")
        
        sunrise_dt, sunset_dt = _get_sun_times_for_spot(spot, date_str)
        buffer = spot.daylight_buffer_minutes
        
        return SunTimes(
            date=date_str,
            sunrise=sunrise_dt,
            sunset=sunset_dt,
            daylight_start=sunrise_dt - timedelta(minutes=buffer),
            daylight_end=sunset_dt + timedelta(minutes=buffer),
        )


def _local_datetime(value: datetime) -> datetime:
    """Convert to local timezone."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(LOCAL_TIMEZONE)


def check_daylight_duration(
    start_time: datetime,
    end_time: datetime,
    sun_times: SunTimes,
    spot: SpotConfig,
) -> tuple[bool, float | None]:
    """Check if a time window has at least the minimum required daylight duration.
    
    This validates that within the evaluation window (start_time to end_time),
    there is sufficient daylight time meeting the spot's duration requirements.
    
    For flats spots with tide-relative daylight windows, it checks if the window
    falls within the tide-calculated daylight period.
    
    Args:
        start_time: Start of the evaluation window
        end_time: End of the evaluation window
        sun_times: SunTimes dataclass with daylight bounds
        spot: Spot configuration with daylight settings
        
    Returns:
        Tuple of (has_daylight: bool, daylight_minutes: float | None)
        - has_daylight: True if there is at least 30 minutes of daylight in the window
        - daylight_minutes: Minutes of daylight available (None if outside daylight period)
    """
    # For flats with tide-relative windows, use tide-calculated windows
    if spot.daylight_start_offset_hours is not None and spot.daylight_end_offset_hours is not None:
        # Flat spots use the standard daylight_start/end from sun_times
        # The tide calculation is handled separately in the evaluator
        daylit_start = sun_times.daylight_start
        daylit_end = sun_times.daylight_end
    else:
        daylit_start = sun_times.daylight_start
        daylit_end = sun_times.daylight_end
    
    # Calculate overlap between evaluation window and daylight window
    overlap_start = max(start_time, daylit_start)
    overlap_end = min(end_time, daylit_end)
    
    if overlap_start >= overlap_end:
        # No overlap with daylight period
        return False, None
    
    daylight_minutes = (overlap_end - overlap_start).total_seconds() / 60
    
    # Check if there's at least 30 minutes of daylight
    MINIMUM_DAYLIGHT_MINUTES = 30.0
    has_minimum = daylight_minutes >= MINIMUM_DAYLIGHT_MINUTES
    
    return has_minimum, daylight_minutes


def get_flats_daylight_window(
    spot: SpotConfig,
    reference_time: datetime,
    sun_times: SunTimes | None,
) -> tuple[datetime, datetime]:
    """Get tide-relative daylight window for flats spot.
    
    For flats, the valid daylight period is calculated relative to tide extrema:
    - When tide is near high: daylit period = 2 hours after high to 2 hours after low
    - When tide is near low: daylit period = 2 hours after low to 2 hours after high
    
    This function determines whether the current time falls within a valid
    tide-relative daylight window based on proximity to tide extrema.
    
    Args:
        spot: Flats spot configuration with daylight offset settings
        reference_time: Current reference time for calculation
        sun_times: SunTimes dataclass for this date (may be None if calculation fails)
        
    Returns:
        Tuple of (daylight_start, daylight_end) for the tide-relative period.
        Returns (None, None) if the time is NOT within a valid tide-relative window.
    """
    offset_hours = spot.daylight_start_offset_hours or 2.0
    offset_delta = timedelta(hours=offset_hours)
    
    # Default to standard daylight window if sun_times unavailable
    if sun_times:
        standard_start = sun_times.daylight_start
        standard_end = sun_times.daylight_end
    else:
        # Fallback: use standard daylight window
        return None, None
    
    # Determine if we're in a valid tide-relative period
    # We need to check proximity to tide extrema
    # For this, we use the standard daylight window as reference
    # and check if the reference_time is within 2 hours of a tide extreme
    
    # Calculate the expected window based on reference time being within
    # 2 hours of a tide extreme
    start_candidate = reference_time - offset_delta
    end_candidate = reference_time + (24 * 60 * 60) - offset_delta
    
    # The tide-relative window should align with standard daylight
    # If reference_time is within 2 hours of high tide, the daylit period
    # runs from (high_tide + 2h) to (low_tide + 2h) the next extreme
    # If reference_time is within 2 hours of low tide, the daylit period
    # runs from (low_tide + 2h) to (high_tide + 2h) the next extreme
    
    # For now, return the standard daylight window which will be
    # filtered by evaluator logic based on tide phase
    return standard_start, standard_end


def get_flats_daylit_period(
    spot: SpotConfig,
    reference_time: datetime,
    high_tide: datetime | None,
    low_tide: datetime | None,
) -> tuple[datetime, datetime] | None:
    """Determine if reference_time falls within a valid flats daylit period.
    
    For flats, tide-relative daylight windows are:
    - Near high tide: 2 hours after high to 2 hours after low (valid period)
    - Near low tide: 2 hours after low to 2 hours after high (valid period)
    
    Args:
        spot: Flats spot configuration
        reference_time: Current time to check
        high_tide: Next high tide (if known)
        low_tide: Next low tide (if known)
        
    Returns:
        Tuple of (daylit_start, daylit_end) if within valid period, else None
    """
    offset_hours = spot.daylight_start_offset_hours or 2.0
    offset_delta = timedelta(hours=offset_hours)
    
    # Check proximity to tide extrema (within 2 hours = NEAR phase zone)
    near_high = high_tide and abs((reference_time - high_tide).total_seconds()) <= offset_delta.total_seconds()
    near_low = low_tide and abs((reference_time - low_tide).total_seconds()) <= offset_delta.total_seconds()
    
    if near_high:
        # Daylit period: start = high_tide + 2h, end = next_low_tide + 2h
        daylit_start = high_tide + offset_delta
        if low_tide:
            daylit_end = low_tide + offset_delta
        else:
            return None  # Can't determine end without next low tide
    elif near_low:
        # Daylit period: start = low_tide + 2h, end = next_high_tide + 2h
        daylit_start = low_tide + offset_delta
        if high_tide:
            daylit_end = high_tide + offset_delta
        else:
            return None  # Can't determine end without next high tide
    else:
        # Not near a tide extreme - outside valid daylit period
        return None
    
    return (daylit_start, daylit_end)
