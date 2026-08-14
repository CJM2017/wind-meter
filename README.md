# Cape Ride OpenClaw Skills

This private Python package supplies three OpenClaw skills:

- `ikitesurf-wind` reads current iKitesurf meters and 1–10 day Blend forecasts.
- `cape-tides` reads and classifies NOAA tide predictions.
- `cape-ride-check` applies deterministic TT and foil preferences to both inputs.

The original CircuitPython matrix-display script is retained, without credentials or device IDs,
at `legacy/circuitpython_code.py`.

## Install

Use Python 3.11 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --editable .
```

Provide fresh personal credentials through the process environment. The credentials committed in
the original file must be rotated because removing them from the current tree does not remove them
from Git history.

```sh
export IKITESURF_API_KEY="..."
export IKITESURF_TOKEN="..."
```

Install or link each directory under `skills/` into the OpenClaw workspace. The console scripts
must be on the OpenClaw process `PATH`.

```sh
openclaw skills install ./skills/ikitesurf-wind
openclaw skills install ./skills/cape-tides
openclaw skills install ./skills/cape-ride-check
```

When using the repository virtual environment, add its `.venv/bin` directory to the Gateway
process `PATH`; otherwise the skills' binary requirements will intentionally keep them disabled.

## Commands

```sh
ikitesurf-wind current --spot all
ikitesurf-wind forecast --spot all --days 3
cape-tides current --spot all
cape-tides forecast --spot all --days 3
cape-ride-check current --profile all
cape-ride-check forecast --profile all --days 3
```

All successful commands write JSON to stdout. Expected failures write a redacted message to stderr
and exit nonzero. `--days` accepts 1 through 10; today is day 1 and 3 is the default.

## Tests

The automated suite is offline and uses redacted fixtures:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

See `docs/api-contracts.md` for the currently validated external response contracts.

The legacy credential returned Blend forecast data during validation, but current observations were
gated with `Wind speed requires paid membership`. Current live values therefore remain unverified
until a rotated credential from the entitled account is configured. The tool reports this condition
as `unavailable`; it does not attempt to reuse legacy device identity or bypass subscription checks.
