"""Command-line interface for the cape-tides skill."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from cape_ride.cli_support import SPOT_CHOICES, forecast_days, run_cli, selected_spots
from cape_ride.config import load_config
from cape_ride.http_client import RequestsJsonHttpClient
from cape_ride.serialization import dumps, to_jsonable
from cape_ride.tides import TideClient
from cape_ride.wind import make_forecast_range

LOCAL_TIMEZONE = ZoneInfo("America/New_York")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the current or forecast tide operation."""
    parser = _parser()
    args = parser.parse_args(argv)
    return run_cli(lambda: _execute(args))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cape-tides",
        description="Fetch and classify NOAA tide predictions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    current = subparsers.add_parser("current", help="Classify current tide phases")
    current.add_argument("--spot", choices=SPOT_CHOICES, default="all")
    forecast = subparsers.add_parser("forecast", help="Return forecast tide periods")
    forecast.add_argument("--spot", choices=SPOT_CHOICES, default="all")
    forecast.add_argument("--days", type=forecast_days, default=3)
    return parser


def _execute(args: argparse.Namespace) -> str:
    config = load_config()
    spots = selected_spots(config, args.spot)
    now = datetime.now(tz=LOCAL_TIMEZONE)
    client = TideClient(RequestsJsonHttpClient())
    if args.command == "current":
        states = tuple(client.get_current(spot, now) for spot in spots)
        return dumps(
            {
                "mode": "current",
                "generated_at": now,
                "states": to_jsonable(states),
            }
        )

    forecast_range = make_forecast_range(now, args.days)
    periods = {
        spot.key: to_jsonable(client.get_forecast_periods(spot, forecast_range))
        for spot in spots
    }
    return dumps(
        {
            "mode": "forecast",
            "generated_at": now,
            "days": args.days,
            "range_start": forecast_range.start,
            "range_end": forecast_range.end,
            "periods": periods,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
