# Validated API contracts

Validated on 2026-08-14 using the repository owner's authenticated personal iKitesurf access. No
credential, cookie, device identifier, or authenticated URL is retained here.

## Current wind

- Endpoint: `GET https://api.weatherflow.com/wxengine/rest/spot/getSpotSetByList`
- Required authentication parameters: `wf_apikey`, `wf_token`
- Required client identifier: an accepted iKitesurf `User-Agent`
- Units requested: wind `kts`, temperature `f`, distance `mi`
- Response status: `status.status_code == 0`
- Tabular contract: `data_names` defines each positional `data_values` row.
- Used fields: `spot_id`, `name`, `timestamp`, `avg`, `lull`, `gust`, `dir`, `dir_text`,
  `status_message`, and `last_wind_ob_utc`.
- The new client intentionally does not retain or send account-specific device identity.
- The legacy credential returned the contract above but gated speed values with
  `Wind speed requires paid membership`. A rotated credential from the entitled account is still
  required to validate non-null current speed values.

## Blend forecast

- Endpoint: `GET https://api.weatherflow.com/wxengine/rest/model/getModelDataBySpot`
- Blend selector: `model_id=-1`
- Confirmed model name: `Blended Numerical Weather Prediction Model`
- Required authentication parameters: `wf_apikey`, `wf_token`
- Used fields: `model_time_local`, `wind_speed`, `wind_gust`, `wind_dir`, and `wind_dir_txt`.
- Live responses for spots 332 and 334 contained approximately ten days of prediction points.
- The client filters the provider response to the requested 1 through 10 local calendar days and
  does not interpolate cadence.

## NOAA tides

- Endpoint: `GET https://api.tidesandcurrents.noaa.gov/api/prod/datagetter`
- Product: `predictions`
- Datum: `MLLW`
- Interval: `hilo`
- Time zone: `lst_ldt`
- Units: `english`
- Used fields: prediction time `t`, height `v`, and high/low type `type`.

Provider contracts are private and may change. Schema drift must produce an explicit error rather
than a guessed result.

The implementation does not test alternate device metadata as a means of changing subscription
entitlements.
