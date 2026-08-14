"""Command-line interface for the ikitesurf-wind skill."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from cape_ride.cli_support import SPOT_CHOICES, forecast_days, run_cli, selected_spots
from cape_ride.config import WindCredentials, load_config
from cape_ride.http_client import RequestsJsonHttpClient
from cape_ride.serialization import dumps, to_jsonable
from cape_ride.wind import WindClient

LOCAL_TIMEZONE = ZoneInfo("America/New_York")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the current or forecast wind operation."""
    parser = _parser()
    args = parser.parse_args(argv)
    return run_cli(lambda: _execute(args))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ikitesurf-wind",
        description="Fetch current iKitesurf wind or Blend forecast data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    current = subparsers.add_parser("current", help="Fetch latest real-time readings")
    current.add_argument("--spot", choices=SPOT_CHOICES, default="all")
    forecast = subparsers.add_parser("forecast", help="Fetch Blend forecast points")
    forecast.add_argument("--spot", choices=SPOT_CHOICES, default="all")
    forecast.add_argument("--days", type=forecast_days, default=3)
    return parser


def _execute(args: argparse.Namespace) -> str:
    config = load_config()
    spots = selected_spots(config, args.spot)
    now = datetime.now(tz=LOCAL_TIMEZONE)
    client = WindClient(RequestsJsonHttpClient(), WindCredentials.from_environment())
    if args.command == "current":
        observations = client.get_current(spots, now)
        return dumps(
            {
                "mode": "current",
                "generated_at": now,
                "observations": to_jsonable(observations),
            }
        )

    forecasts = []
    forecast_range = None
    for spot in spots:
        forecast, current_range = client.get_forecast(spot, args.days, now)
        forecasts.append(forecast)
        forecast_range = forecast_range or current_range
    return dumps(
        {
            "mode": "forecast",
            "generated_at": now,
            "days": args.days,
            "range_start": forecast_range.start if forecast_range else now,
            "range_end": forecast_range.end if forecast_range else now,
            "forecasts": to_jsonable(forecasts),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
