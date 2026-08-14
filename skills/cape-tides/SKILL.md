---
name: cape-tides
description: Fetch and classify current or 1 through 10 day NOAA tide predictions for the configured Cape Cod riding spots.
metadata: {"openclaw":{"requires":{"bins":["cape-tides"]}}}
---

# Cape Tides

Use this skill when the user asks for current tide state or future tide phases at Wall, Pond, Slick,
or Flats.

Run exactly one of:

```text
cape-tides current --spot all
cape-tides current --spot slick
cape-tides forecast --spot all --days 3
cape-tides forecast --spot flats --days 10
```

`--days` accepts 1 through 10 and defaults to 3. Today is day 1. The tool derives `near_high`,
`near_low`, `mid_rising`, and `mid_falling` with two-hour buffers around NOAA high and low tide
predictions.

Read JSON from stdout. Report local timestamps and the configured NOAA station. Tide data by itself
is not a ride recommendation; use `cape-ride-check` to combine it with wind and rider preferences.

