"""Daylight calculation module that supports arbitrary locations.

This module provides functionality to calculate sunrise, sunset, and
daylight window times for any location given latitude and longitude coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import acos, cos, sin
from zoneinfo import ZoneInfo

LOCAL_TIMEZONE = ZoneInfo("America/New_York")

# Default buffer minutes
DEFAULT_BUFFER_MINUTES = 30


@dataclass
class SunTimes:
    """Sun rise and set times for a given day."""

    date: str
    sunrise: datetime
    sunset: datetime
    daylight_start: datetime
    daylight_end: datetime


def _calculate_sun_times(lat: float, lon: float, date_str: str, buffer_minutes: int = DEFAULT_BUFFER_MINUTES) -> SunTimes:
    """Calculate sunrise and sunset times using solar equations.
    
    Uses simplified but accurate calculation based on NOAA algorithms.
    Returns times in the local timezone (America/New_York).
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        date_str: Date in YYYY-MM-DD format
        buffer_minutes: Minutes to add before sunrise and after sunset
        
    Returns:
        SunTimes dataclass with computed values
    """
    # Parse the date
    try:
        year, month, day = map(int, date_str.split('-'))
    except (ValueError, IndexError):
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
    
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
        raise ValueError(f"Invalid month: {month}")
    
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
    zenith_correction = 90.833  # accounts for atmospheric refraction
    sunrise_minutes = 720 - 4 * (lon + hour_angle)
    sunset_minutes = 720 - 4 * (lon - hour_angle)
    
    # Convert to datetime
    def minutes_to_datetime(minutes: float) -> datetime:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return datetime(year, month, day, hours, mins, tzinfo=ZoneInfo("UTC")).astimezone(LOCAL_TIMEZONE)
    
    sunrise_dt = minutes_to_datetime(sunrise_minutes)
    sunset_dt = minutes_to_datetime(sunset_minutes)
    
    return SunTimes(
        date=date_str,
        sunrise=sunrise_dt,
        sunset=sunset_dt,
        daylight_start=sunrise_dt - timedelta(minutes=buffer_minutes),
        daylight_end=sunset_dt + timedelta(minutes=buffer_minutes),
    )


def get_daylight(lat: float, lon: float, date_str: str, buffer_minutes: int = DEFAULT_BUFFER_MINUTES) -> SunTimes:
    """Get daylight information for a location.
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        date_str: Date in YYYY-MM-DD format
        buffer_minutes: Minutes to add before sunrise and after sunset
        
    Returns:
        SunTimes dataclass with computed values
    """
    return _calculate_sun_times(lat, lon, date_str, buffer_minutes)