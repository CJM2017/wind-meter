---
name: ikitesurf-wind
description: Fetch the latest configured Cape Cod iKitesurf wind-meter readings or authenticated Blend forecasts for 1 through 10 local calendar days.
metadata: {"openclaw":{"requires":{"bins":["ikitesurf-wind"],"env":["IKITESURF_API_KEY","IKITESURF_TOKEN"]}}}
---

# iKitesurf Wind

Use this skill when the user asks for current wind-meter data or the iKitesurf Blend forecast for
Wall, Pond, Slick, or Flats.

Run exactly one of:

```text
ikitesurf-wind current --spot all
ikitesurf-wind current --spot wall
ikitesurf-wind forecast --spot all --days 3
ikitesurf-wind forecast --spot flats --days 10
```

`--days` accepts 1 through 10 and defaults to 3. Today is day 1. Current mode returns only the
latest observation; it does not return history or start a monitor.

Read JSON from stdout. Summarize the values, timestamps, provider status, and units without exposing
credentials or authenticated request URLs. Treat `stale` and `unavailable` as unknown data. Do not
turn raw wind into a ride recommendation; use the `cape-ride-check` skill for that.

