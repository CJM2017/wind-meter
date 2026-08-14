"""Load non-secret spot rules and secret provider credentials."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Mapping

from cape_ride.errors import ConfigurationError
from cape_ride.models import TidePhase

DEFAULT_USER_AGENT = "iKitesurf/1777 CFNetwork/3826.500.131 Darwin/24.5.0"
SUPPORTED_TIDE_MODES = frozenset({"any", "allowed", "directional"})


@dataclass(frozen=True)
class WindCredentials:
    """Credentials required by the authenticated iKitesurf endpoints."""

    api_key: str
    token: str
    user_agent: str

    @classmethod
    def from_environment(cls) -> WindCredentials:
        """Read credentials without exposing their values in errors."""
        api_key = os.getenv("IKITESURF_API_KEY")
        token = os.getenv("IKITESURF_TOKEN")
        if not api_key or not token:
            raise ConfigurationError(
                "IKITESURF_API_KEY and IKITESURF_TOKEN must both be configured"
            )
        return cls(
            api_key=api_key,
            token=token,
            user_agent=os.getenv("IKITESURF_USER_AGENT", DEFAULT_USER_AGENT),
        )


@dataclass(frozen=True)
class SpotConfig:
    """Provider mappings for one riding location."""

    key: str
    provider_spot_id: int
    provider_name: str
    tide_station_id: str
    tide_station_name: str


@dataclass(frozen=True)
class RideProfile:
    """Deterministic wind and tide rules for one discipline at one spot."""

    key: str
    spot: str
    discipline: str
    minimum_average_knots: float
    directions: frozenset[str]
    tide_mode: str
    preferred_tide_phases: frozenset[TidePhase]
    allowed_tide_phases: frozenset[TidePhase]
    lower_tide_directions: frozenset[str]
    higher_tide_directions: frozenset[str]


@dataclass(frozen=True)
class AppConfig:
    """Complete non-secret application configuration."""

    spots: Mapping[str, SpotConfig]
    profiles: Mapping[str, RideProfile]


def load_config() -> AppConfig:
    """Load and validate the packaged TOML configuration."""
    resource = files("cape_ride.resources").joinpath("spots.toml")
    with resource.open("rb") as config_file:
        raw = tomllib.load(config_file)

    raw_spots = _mapping(raw.get("spots"), "spots")
    raw_profiles = _mapping(raw.get("profiles"), "profiles")
    spots = {key: _parse_spot(key, value) for key, value in raw_spots.items()}
    profiles = {
        key: _parse_profile(key, value, spots) for key, value in raw_profiles.items()
    }
    return AppConfig(
        spots=MappingProxyType(spots),
        profiles=MappingProxyType(profiles),
    )


def _parse_spot(key: str, value: object) -> SpotConfig:
    item = _mapping(value, f"spots.{key}")
    return SpotConfig(
        key=key,
        provider_spot_id=_integer(item.get("provider_spot_id"), "provider_spot_id"),
        provider_name=_string(item.get("provider_name"), "provider_name"),
        tide_station_id=_string(item.get("tide_station_id"), "tide_station_id"),
        tide_station_name=_string(item.get("tide_station_name"), "tide_station_name"),
    )


def _parse_profile(
    key: str,
    value: object,
    spots: Mapping[str, SpotConfig],
) -> RideProfile:
    item = _mapping(value, f"profiles.{key}")
    spot = _string(item.get("spot"), "spot")
    if spot not in spots:
        raise ConfigurationError(f"Profile {key} references unknown spot {spot}")
    tide_mode = _string(item.get("tide_mode"), "tide_mode")
    if tide_mode not in SUPPORTED_TIDE_MODES:
        raise ConfigurationError(f"Profile {key} has unsupported tide mode {tide_mode}")
    return RideProfile(
        key=key,
        spot=spot,
        discipline=_string(item.get("discipline"), "discipline"),
        minimum_average_knots=_number(
            item.get("minimum_average_knots"), "minimum_average_knots"
        ),
        directions=frozenset(_strings(item.get("directions"), "directions")),
        tide_mode=tide_mode,
        preferred_tide_phases=_tide_phases(item.get("preferred_tide_phases")),
        allowed_tide_phases=_tide_phases(item.get("allowed_tide_phases")),
        lower_tide_directions=frozenset(
            _strings(item.get("lower_tide_directions", []), "lower_tide_directions")
        ),
        higher_tide_directions=frozenset(
            _strings(item.get("higher_tide_directions", []), "higher_tide_directions")
        ),
    )


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigurationError(f"{name} must be a TOML table")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{name} must be a non-empty string")
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigurationError(f"{name} must be a number")
    return float(value)


def _strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(f"{name} must be an array of strings")
    return value


def _tide_phases(value: object) -> frozenset[TidePhase]:
    names = _strings(value if value is not None else [], "tide phases")
    try:
        return frozenset(TidePhase(name) for name in names)
    except ValueError as error:
        raise ConfigurationError("A profile contains an unknown tide phase") from error

