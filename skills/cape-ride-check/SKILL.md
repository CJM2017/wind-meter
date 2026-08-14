---
name: cape-ride-check
description: Deterministically evaluate current conditions or 1 through 10 day rideable windows for configured Cape Cod TT and foil profiles using iKitesurf wind and NOAA tides.
metadata: {"openclaw":{"requires":{"bins":["cape-ride-check"],"env":["IKITESURF_API_KEY","IKITESURF_TOKEN"]}}}
---

# Cape Ride Check

Use this skill when the user asks whether it is rideable now or when the next rideable TT or foil
windows occur.

Run exactly one of:

```text
cape-ride-check current --profile all
cape-ride-check current --profile wall:foil
cape-ride-check forecast --profile all --days 3
cape-ride-check forecast --profile flats:tt --days 10
```

Supported profiles are `wall:tt`, `wall:foil`, `pond:tt`, `pond:foil`, `slick:tt`, and `flats:tt`.
Do not invent Slick or Flats foil assessments. `--days` accepts 1 through 10 and defaults to 3.

Read JSON from stdout and preserve the tool's tri-state result:

- `rideable`: the configured wind and required tide gates are met.
- `not_rideable`: available data deterministically fails at least one gate.
- `unknown`: required data is stale, missing, or unavailable.

Explain the evidence returned by the tool. Do not overrule its deterministic result, expose
credentials, or imply that a weather recommendation guarantees personal safety.

