DEMO_WEATHER = {
    "delhi": {"temperature_c": 31, "condition": "Sunny", "humidity_percent": 38},
    "london": {"temperature_c": 14, "condition": "Light rain", "humidity_percent": 76},
    "new york": {"temperature_c": 19, "condition": "Cloudy", "humidity_percent": 61},
    "san francisco": {"temperature_c": 16, "condition": "Foggy", "humidity_percent": 72},
}


def get_weather(city: str) -> dict[str, str | int]:
    """Return deterministic demo data so this tool works fully offline."""
    weather = DEMO_WEATHER.get(city.strip().lower())
    if weather is None:
        return {"city": city, "status": "unavailable", "message": "No offline demo weather data is available."}
    return {"city": city, "source": "offline demo data", **weather}
