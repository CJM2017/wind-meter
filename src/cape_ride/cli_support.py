"""Shared command-line parsing and provider construction."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from cape_ride.config import AppConfig, RideProfile, SpotConfig
from cape_ride.errors import CapeRideError

SPOT_CHOICES = ("all", "wall", "pond", "slick", "flats")
PROFILE_CHOICES = (
    "all",
    "wall:tt",
    "wall:foil",
    "pond:tt",
    "pond:foil",
    "slick:tt",
    "flats:tt",
)


def forecast_days(value: str) -> int:
    """Argparse converter for the inclusive 1 through 10 day range."""
    try:
        days = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("days must be an integer from 1 to 10") from error
    if not 1 <= days <= 10:
        raise argparse.ArgumentTypeError("days must be between 1 and 10")
    return days


def selected_spots(config: AppConfig, key: str) -> tuple[SpotConfig, ...]:
    """Resolve one spot or all spots in configured order."""
    if key == "all":
        return tuple(config.spots.values())
    return (config.spots[key],)


def selected_profiles(config: AppConfig, key: str) -> tuple[RideProfile, ...]:
    """Resolve one profile or all supported profiles in configured order."""
    if key == "all":
        return tuple(config.profiles.values())
    return (config.profiles[key],)


def run_cli(operation: Callable[[], object]) -> int:
    """Render expected failures without leaking request URLs or credentials."""
    try:
        result = operation()
    except (CapeRideError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(result)
    return 0
