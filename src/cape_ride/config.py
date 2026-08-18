"""Load non-secret spot rules and secret provider credentials."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Mapping, Union, Any, Dict, List

from cape_ride.errors import ConfigurationError
from cape_ride.models import TidePhase

DEFAULT_USER_AGENT = "iKitesurf/1777 CFNetwork/3826.500.131 Darwin/24.5.0"
SUPPORTED_TIDE_MODES = frozenset({"any", "allowed", "directional"})

# Try to import tomllib (Python 3.11+) or tomli
TOMLParser = None
try:
    import tomllib
    TOMLParser = tomllib.load
except ImportError:
    try:
        import tomli
        TOMLParser = tomli.load
    except ImportError:
        # Fallback: minimal TOML parser for basic config files
        TOMLParser = None


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


def _simple_toml_parse(content: str) -> Dict[str, Any]:
    """Minimal TOML parser for basic config structures."""
    result: Dict[str, Any] = {}
    current_section = result
    section_path = []
    
    for line in content.splitlines():
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
        
        # Section headers [parent.child]
        if line.startswith('[') and line.endswith(']'):
            section_name = line[1:-1]
            current_section = result
            path_parts = section_name.split('.')
            for part in path_parts:
                if part not in current_section:
                    current_section[part] = {}
                current_section = current_section[part]
            continue
        
        # Key-value pairs
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # Parse different TOML types
            parsed_value = _parse_toml_value(value)
            current_section[key] = parsed_value
    
    return result


def _parse_toml_value(value: str) -> Union[str, int, float, bool, List, Dict]:
    """Parse a TOML value."""
    if not value:
        return ""
    
    # Boolean
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    
    # String (quoted)
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1].strip()
    
    # Array - simplified parsing
    if value.startswith('[') and value.endswith(']'):
        items_str = value[1:-1].strip()
        if not items_str:
            return []
        # Split by comma, but handle quoted strings properly
        items = []
        current = ''
        in_string = False
        string_char = None
        
        for char in items_str:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
                current += char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
                current += char
            elif char == ',' and not in_string:
                if current.strip():
                    items.append(_parse_toml_value(current.strip()))
                current = ''
            else:
                current += char
        
        if current.strip():
            items.append(_parse_toml_value(current.strip()))
        
        return items
    
    # Integer or float
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    
    # Return as string
    return value.strip().strip('"').strip("'")


def _load_toml_file(filepath: str) -> Dict[str, Any]:
    """Load a TOML file using available parser."""
    if TOMLParser:
        with open(filepath, 'rb') as f:
            return TOMLParser(f)
    else:
        with open(filepath, 'r') as f:
            return _simple_toml_parse(f.read())


def load_config() -> AppConfig:
    """Load and validate the packaged TOML configuration."""
    import sys
    from importlib import resources
    
    # Try to read from package resources
    try:
        # Python 3.9+ style
        with resources.files("cape_ride.resources").joinpath("spots.toml").open("r", encoding="utf-8") as f:
            toml_content = f.read()
    except Exception:
        # Fallback: try direct file read
        toml_content = ""
    
    if TOMLParser:
        import io
        raw = TOMLParser(io.BytesIO(toml_content.encode()))
    else:
        raw = _simple_toml_parse(toml_content)

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
