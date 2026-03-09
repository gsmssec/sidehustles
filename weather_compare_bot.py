import json
import logging
import os
from datetime import datetime
from typing import Any


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FOG_WEATHER_CODES = {45, 48}
POLLEN_FIELDS = [
    "alder_pollen",
    "birch_pollen",
    "grass_pollen",
    "mugwort_pollen",
    "olive_pollen",
    "ragweed_pollen",
]


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _today_city_stats(hourly: dict[str, list[Any]], field: str) -> dict[str, float | None]:
    values = [v for v in hourly.get(field, []) if isinstance(v, (int, float))]
    if not values:
        return {"avg": None, "max": None, "current": None}

    return {
        "avg": round(sum(values) / len(values), 1),
        "max": round(max(values), 1),
        "current": round(values[0], 1),
    }


def _weather_label(code: int | None) -> str:
    labels = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing rime fog",
        51: "light drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        71: "slight snow",
        75: "heavy snow",
        95: "thunderstorm",
    }
    return labels.get(code, "mixed conditions")


def _allergy_level(pollen_hourly: dict[str, list[Any]]) -> str:
    max_reading = 0.0
    for field in POLLEN_FIELDS:
        values = [v for v in pollen_hourly.get(field, []) if isinstance(v, (int, float))]
        if values:
            max_reading = max(max_reading, max(values))

    if max_reading >= 80:
        return "High"
    if max_reading >= 25:
        return "Medium"
    return "Low"


def _validate_canadian_city(result: dict[str, Any], city_name: str) -> None:
    country_code = result.get("country_code")
    if country_code != "CA":
        raise ValueError(f"City '{city_name}' is not in Canada based on geocoding results.")


def _requests_session() -> Any:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    total_retries = int(os.getenv("WEATHER_HTTP_RETRIES", "3"))
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    connect_timeout = float(os.getenv("WEATHER_CONNECT_TIMEOUT_SEC", "10"))
    read_timeout = float(os.getenv("WEATHER_READ_TIMEOUT_SEC", "45"))
    session = _requests_session()
    response = session.get(url, params=params, timeout=(connect_timeout, read_timeout))
    response.raise_for_status()
    return response.json()


def get_city_weather(city_name: str) -> dict[str, Any]:
    timezone = os.getenv("TIMEZONE") or "America/Toronto"

    geo_data = _get_json(
        GEOCODING_URL,
        {
            "name": city_name,
            "count": 1,
            "language": "en",
            "format": "json",
        },
    )
    results = geo_data.get("results") or []
    if not results:
        raise ValueError(f"Could not geocode city: {city_name}")

    location = results[0]
    _validate_canadian_city(location, city_name)

    lat = location["latitude"]
    lon = location["longitude"]

    forecast_data = _get_json(
        FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "apparent_temperature,uv_index,precipitation_probability,weather_code,visibility",
            "hourly": "apparent_temperature,uv_index,precipitation_probability,weather_code,visibility",
            "timezone": timezone,
            "forecast_days": 1,
        },
    )

    pollen_data = _get_json(
        AIR_QUALITY_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(POLLEN_FIELDS),
            "timezone": timezone,
            "forecast_days": 1,
        },
    )

    current = forecast_data.get("current", {})
    hourly = forecast_data.get("hourly", {})

    weather_code = current.get("weather_code")
    visibility = current.get("visibility")
    fog_risk = (
        (isinstance(visibility, (int, float)) and visibility < 1000)
        or weather_code in FOG_WEATHER_CODES
    )

    return {
        "city": location.get("name", city_name),
        "province": location.get("admin1"),
        "country": location.get("country"),
        "timezone": timezone,
        "latitude": lat,
        "longitude": lon,
        "current": {
            "real_feel_c": current.get("apparent_temperature"),
            "uv_index": current.get("uv_index"),
            "rain_probability_pct": current.get("precipitation_probability"),
            "visibility_m": visibility,
            "weather_code": weather_code,
            "weather_label": _weather_label(weather_code),
            "fog_risk": fog_risk,
            "allergy_index": _allergy_level(pollen_data.get("hourly", {})),
        },
        "today_stats": {
            "real_feel": _today_city_stats(hourly, "apparent_temperature"),
            "uv_index": _today_city_stats(hourly, "uv_index"),
            "rain_probability": _today_city_stats(hourly, "precipitation_probability"),
        },
    }


def build_weather_payload(city1_data: dict[str, Any], city2_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": datetime.now().date().isoformat(),
        "comparison_basis": [
            "real_feel",
            "uv_index",
            "allergy_index",
            "rain_probability",
            "fog_and_hazards",
        ],
        "cities": [city1_data, city2_data],
    }


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", "")
    if text:
        return text.strip()

    output = getattr(response, "output", []) or []
    chunks: list[str] = []
    for item in output:
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
    return " ".join(part.strip() for part in chunks if part.strip())


def _fallback_summary(payload: dict[str, Any]) -> str:
    city_a, city_b = payload["cities"]

    def score(city: dict[str, Any]) -> float:
        current = city["current"]
        rain = current.get("rain_probability_pct") or 0
        uv = current.get("uv_index") or 0
        visibility = current.get("visibility_m") or 10000
        allergy = current.get("allergy_index")

        allergy_penalty = {"Low": 0, "Medium": 8, "High": 16}.get(allergy, 5)
        fog_penalty = 10 if current.get("fog_risk") else 0
        rain_penalty = min(float(rain), 100) * 0.2
        uv_penalty = max(float(uv) - 6, 0) * 3
        visibility_penalty = 5 if visibility < 1000 else 0

        return 100 - (allergy_penalty + fog_penalty + rain_penalty + uv_penalty + visibility_penalty)

    score_a = score(city_a)
    score_b = score(city_b)

    better = city_a if score_a >= score_b else city_b
    other = city_b if better is city_a else city_a

    return (
        f"{better['city']} looks better overall today based on lower weather-related travel risk. "
        f"Compared with {other['city']}, it currently has more favorable real-feel, UV/allergy exposure, and rain chances. "
        f"If traveling to either city, watch for {better['current']['weather_label']} in {better['city']} and "
        f"{other['current']['weather_label']} in {other['city']}, especially where visibility drops or fog is present."
    )


def summarize_with_openai(payload: dict[str, Any]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL") or "gpt-5-mini"

    if not api_key:
        logging.warning("OPENAI_API_KEY is missing. Using fallback summary.")
        return _fallback_summary(payload)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a weather comparison assistant. Output plain text only. "
                        "Return exactly 2-3 sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Compare these two Canadian cities for today. Choose which city is better today "
                        "in terms of real feel, UV, allergy index proxy, and probability of rain. "
                        "Also include travel cautions for fog or other weather hazards. "
                        "Keep it to 2-3 sentences. Data: "
                        + json.dumps(payload, separators=(",", ":"))
                    ),
                },
            ],
        )
        summary = _extract_response_text(response)
        if not summary:
            raise ValueError("OpenAI response text was empty")
        return summary
    except Exception as exc:
        logging.exception("OpenAI summarization failed. Falling back. Error: %s", exc)
        return _fallback_summary(payload)


def send_sms(summary: str) -> None:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("SMS_TO_NUMBER")

    required = {
        "TWILIO_ACCOUNT_SID": account_sid,
        "TWILIO_AUTH_TOKEN": auth_token,
        "TWILIO_FROM_NUMBER": from_number,
        "SMS_TO_NUMBER": to_number,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(f"Missing Twilio env vars: {', '.join(missing)}")

    from twilio.rest import Client

    client = Client(account_sid, auth_token)
    client.messages.create(body=summary, from_=from_number, to=to_number)


def send_email(summary: str, details: str) -> None:
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("EMAIL_FROM")
    to_email = os.getenv("EMAIL_TO")

    required = {
        "SENDGRID_API_KEY": api_key,
        "EMAIL_FROM": from_email,
        "EMAIL_TO": to_email,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(f"Missing SendGrid env vars: {', '.join(missing)}")

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject="Hourly Canada Weather Comparison",
        plain_text_content=f"{summary}\n\n{details}",
    )

    sg = SendGridAPIClient(api_key)
    sg.send(message)


def _format_details(payload: dict[str, Any], summary: str) -> str:
    lines = [
        f"Timestamp: {datetime.now().isoformat()}",
        f"Date: {payload['date']}",
        "",
        f"Summary: {summary}",
        "",
    ]
    for city in payload["cities"]:
        current = city["current"]
        lines.extend(
            [
                f"{city['city']}, {city.get('province') or ''}",
                f"  Real feel: {current.get('real_feel_c')}C",
                f"  UV index: {current.get('uv_index')}",
                f"  Allergy index proxy: {current.get('allergy_index')}",
                f"  Rain probability: {current.get('rain_probability_pct')}%",
                f"  Visibility: {current.get('visibility_m')}m",
                f"  Conditions: {current.get('weather_label')}",
                f"  Fog risk: {'Yes' if current.get('fog_risk') else 'No'}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def main() -> None:
    _setup_logging()
    from dotenv import load_dotenv

    load_dotenv()

    city_1 = os.getenv("CITY_1")
    city_2 = os.getenv("CITY_2")
    if not city_1 or not city_2:
        raise ValueError("CITY_1 and CITY_2 must be set.")

    logging.info("Fetching weather for %s and %s", city_1, city_2)
    city1_data = get_city_weather(city_1)
    city2_data = get_city_weather(city_2)

    payload = build_weather_payload(city1_data, city2_data)
    summary = summarize_with_openai(payload)
    details = _format_details(payload, summary)

    logging.info("Sending SMS notification")
    send_sms(summary)

    logging.info("Sending email notification")
    send_email(summary, details)

    logging.info("Weather compare notification flow completed successfully")


if __name__ == "__main__":
    main()
