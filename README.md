# Weather Compare Bot

This project contains a Python bot that compares weather for two Canadian cities, summarizes which city is better for the day using the OpenAI API, and sends that summary by email every hour via GitHub Actions.

## How the bot was created

The bot was implemented as a standalone script (`weather_compare_bot.py`) so it can run both locally and in CI without changing your existing `main.py`.

The implementation is broken into clear functions:
- `get_city_weather(city_name)`: Fetches city geocoding + weather + pollen data from Open-Meteo APIs.
- `build_weather_payload(city1_data, city2_data)`: Normalizes both cities into one comparison payload.
- `summarize_with_openai(payload)`: Calls OpenAI Responses API for a 2-3 sentence comparison summary.
- `send_email(summary, details)`: Sends summary + detail snapshot using SendGrid.
- `main()`: Orchestrates the full pipeline in one run.

## What the Python code does

1. Loads configuration from environment variables (`CITY_1`, `CITY_2`, API keys, and email settings).
2. Geocodes each city with Open-Meteo geocoding and validates they are in Canada.
3. Pulls today's weather data from Open-Meteo forecast and air-quality endpoints.
4. Extracts and computes key comparison factors:
- Real feel (`apparent_temperature`)
- UV index (`uv_index`)
- Rain probability (`precipitation_probability`)
- Fog risk (low visibility and fog weather codes)
- Allergy index proxy (derived from pollen signals)
5. Builds one compact JSON payload for LLM comparison.
6. Requests a short natural-language summary from OpenAI.
7. Falls back to a rule-based summary if OpenAI is unavailable.
8. Sends an email notification via SendGrid.
9. Logs status so failures are visible in Actions logs.

## Resilience and reliability

The weather HTTP client includes retry/backoff and configurable timeouts to reduce intermittent API timeout failures in GitHub Actions.

Optional tuning environment variables:
- `WEATHER_HTTP_RETRIES` (default: `3`)
- `WEATHER_CONNECT_TIMEOUT_SEC` (default: `10`)
- `WEATHER_READ_TIMEOUT_SEC` (default: `45`)

## GitHub Actions workflow

Workflow file: `.github/workflows/weather-compare-hourly.yml`

Triggers:
- `workflow_dispatch`: manual run from GitHub UI
- `schedule`: hourly cron (`0 * * * *`, UTC)

Runtime steps:
1. Checkout repository.
2. Setup Python 3.13.
3. Install dependencies from `requirements.txt`.
4. Run `python weather_compare_bot.py` with secrets injected as environment variables.

Important: scheduled runs execute from your repository default branch, so feature-branch changes must be merged via PR to affect hourly runs.

## Required GitHub secrets

Core configuration:
- `CITY_1`
- `CITY_2`
- `OPENAI_API_KEY`
- `SENDGRID_API_KEY`
- `EMAIL_FROM`
- `EMAIL_TO`

Optional configuration:
- `TIMEZONE` (for example `America/Toronto`)
- `OPENAI_MODEL` (for example `gpt-5-mini`)
- `WEATHER_HTTP_RETRIES`
- `WEATHER_CONNECT_TIMEOUT_SEC`
- `WEATHER_READ_TIMEOUT_SEC`

## Project structure

- `weather_compare_bot.py`: main weather-compare + summarize + email pipeline.
- `.github/workflows/weather-compare-hourly.yml`: hourly automation workflow.
- `tests/test_weather_compare_bot.py`: unit tests for allergy scoring and fallback summary logic.
- `requirements.txt`: runtime dependencies.
- `main.py`: existing file kept untouched.

## Local testing

1. Install dependencies:
   `python -m pip install -r requirements.txt`
2. Set required environment variables (or use `.env`).
3. Run bot:
   `python weather_compare_bot.py`
4. Run tests:
   `python -m unittest discover -s tests -v`
