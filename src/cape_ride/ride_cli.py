"""Command-line interface for deterministic rideability evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from cape_ride.cli_support import (
    PROFILE_CHOICES,
    forecast_days,
    run_cli,
    selected_profiles,
)
from cape_ride.config import WindCredentials, load_config
from cape_ride.evaluator import RideService
from cape_ride.http_client import RequestsJsonHttpClient
from cape_ride.serialization import dumps, to_jsonable
from cape_ride.sunrise_sunset import SunriseSunsetClient
from cape_ride.tides import TideClient
from cape_ride.wind import WindClient

LOCAL_TIMEZONE = ZoneInfo("America/New_York")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the current or forecast rideability operation."""
    parser = _parser()
    args = parser.parse_args(argv)
    return run_cli(lambda: _execute(args))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cape-ride-check",
        description="Evaluate Cape Cod wind and tide preferences.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    current = subparsers.add_parser("current", help="Evaluate current conditions")
    current.add_argument("--profile", choices=PROFILE_CHOICES, default="all")
    forecast = subparsers.add_parser("forecast", help="Find rideable forecast windows")
    forecast.add_argument("--profile", choices=PROFILE_CHOICES, default="all")
    forecast.add_argument("--days", type=forecast_days, default=3)
    forecast.add_argument("--multi-model", action="store_true", help="Use multi-model forecasting")
    forecast.add_argument("--models", action="append", type=int, default=[], help="Model IDs to query (can specify multiple times, e.g., --models -1 --models 2 --models 1)")
    return parser


def _execute(args: argparse.Namespace) -> str:
    config = load_config()
    profiles = selected_profiles(config, args.profile)
    now = datetime.now(tz=LOCAL_TIMEZONE)
    http_client = RequestsJsonHttpClient()
    service = RideService(
        config=config,
        wind_client=WindClient(http_client, WindCredentials.from_environment()),
        tide_client=TideClient(http_client),
        sunrise_client=SunriseSunsetClient(http_client),
    )
    if args.command == "current":
        assessments = service.get_current(profiles, now)
        return dumps(
            {
                "mode": "current",
                "generated_at": now,
                "assessments": to_jsonable(assessments),
            }
        )

    # Parse model IDs if provided
    model_ids = args.models if args.models else None
    if model_ids is not None and len(model_ids) == 0:
        model_ids = None
    
    forecasts, forecast_range = service.get_forecast(
        profiles, 
        args.days, 
        now,
        use_multi_model=args.multi_model,
        model_ids=model_ids,
    )
    return dumps(
        {
            "mode": "forecast",
            "generated_at": now,
            "days": args.days,
            "range_start": forecast_range.start,
            "range_end": forecast_range.end,
            "multi_model": args.multi_model,
            "forecasts": to_jsonable(forecasts),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
