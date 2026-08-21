---
name: get-daylight
description: Get solar daylight information for any specified location given coordinates.
metadata: {"openclaw":{"requires":{"bins":["get-daylight"]}}}
---

# Get Daylight

Use this skill to calculate sunrise, sunset, and daylight window times for any location given latitude and longitude coordinates.

Run exactly one of:

```text
get-daylight --lat 41.7026 --lon -70.3011
get-daylight --lat 41.7026 --lon -70.3011 --date 2026-08-21
get-daylight --lat 41.7026 --lon -70.3011 --buffer 20
```

Parameters:
- `--lat` (required): Latitude coordinate (decimal degrees)
- `--lon` (required): Longitude coordinate (decimal degrees)
- `--date` (optional): Date in YYYY-MM-DD format. Defaults to today.
- `--buffer` (optional): Daylight buffer in minutes before sunrise and after sunset. Defaults to 30.

Output format:
- `date`: The date calculated for (YYYY-MM-DD)
- `sunrise`: Sunrise time in local timezone
- `sunset`: Sunset time in local timezone
- `daylight_start`: Sunrise minus buffer minutes
- `daylight_end`: Sunset plus buffer minutes

The daylight window (daylight_start to daylight_end) represents the period when there is significant daylight, accounting for atmospheric refraction and user-specified buffer time.

Examples:

```bash
# Get daylight for Barnstable, MA (default date, default 30-min buffer)
get-daylight --lat 41.7026 --lon -70.3011

# Get daylight for a specific date and custom buffer
get-daylight --lat 41.7026 --lon -70.3011 --date 2026-12-21 --buffer 45

# Get daylight for New York City
get-daylight --lat 40.7128 --lon -74.0060