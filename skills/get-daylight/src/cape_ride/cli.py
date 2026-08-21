"""Command-line interface for get-daylight skill."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Sequence

from zoneinfo import ZoneInfo

from .get_daylight import DEFAULT_BUFFER_MINUTES, get_daylight

LOCAL_TIMEZONE = ZoneInfo("America/New_York")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="get-daylight",
        description="Get solar daylight information for any specified location given coordinates.",
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="Latitude coordinate (decimal degrees)",
    )
    parser.add_argument(
        "--lon",
        type=float,
        required=True,
        help="Longitude coordinate (decimal degrees)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--buffer",
        type=int,
        default=DEFAULT_BUFFER_MINUTES,
        help=f"Daylight buffer in minutes before sunrise and after sunset. Defaults to {DEFAULT_BUFFER_MINUTES}.",
    )
    return parser.parse_args(argv)


def _format_time(dt) -> str:
    """Format datetime for JSON output."""
    return dt.isoformat()


def _execute(args: argparse.Namespace) -> str:
    """Execute the get-daylight command and return JSON output."""
    try:
        date_str = args.date if args.date else datetime.now(tz=LOCAL_TIMEZONE).strftime("%Y-%m-%d")
        
        sun_times = get_daylight(
            lat=args.lat,
            lon=args.lon,
            date_str=date_str,
            buffer_minutes=args.buffer,
        )
        
        output = {
            "date": sun_times.date,
            "location": {
                "latitude": args.lat,
                "longitude": args.lon,
            },
            "sunrise": _format_time(sun_times.sunrise),
            "sunset": _format_time(sun_times.sunset),
            "daylight_start": _format_time(sun_times.daylight_start),
            "daylight_end": _format_time(sun_times.daylight_end),
            "buffer_minutes": args.buffer,
        }
        
        return json.dumps(output)
    except ValueError as e:
        return json.dumps({"error": str(e)})


def main(argv: Sequence[str] | None = None) -> int:
    """Run the get-daylight command."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    result = _execute(args)
    print(result)
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
