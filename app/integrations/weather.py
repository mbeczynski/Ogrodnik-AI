"""Klient do Open-Meteo (bez klucza API, darmowy do użytku niekomercyjnego)."""

from typing import Any

import httpx

from .. import runtime_settings as rs

BASE_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherClient:
    def __init__(self, lat: float | None = None, lon: float | None = None):
        self.lat = lat if lat is not None else rs.get_float("garden_lat")
        self.lon = lon if lon is not None else rs.get_float("garden_lon")

    async def get_current_and_forecast(self) -> dict[str, Any]:
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "current": "temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m",
            "hourly": "temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m",
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 3,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def extract_current_snapshot(data: dict[str, Any]) -> dict[str, Any]:
        current = data.get("current", {})
        return {
            "timestamp": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "precipitation_mm": current.get("precipitation"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_kph": current.get("wind_speed_10m"),
        }
