from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlmodel import select

from ..analysis import generate_and_store_insight
from ..db import get_session
from ..integrations.weather import WeatherClient
from ..models import GardenAction, Insight, MowingEvent, WateringEvent, WeatherSnapshot

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/timeline")
def get_timeline(days: int = 14) -> list[dict[str, Any]]:
    """Łączy wszystkie typy zdarzeń w jedną chronologiczną osię czasu."""
    since = datetime.utcnow() - timedelta(days=days)
    items: list[dict[str, Any]] = []
    with get_session() as session:
        watering = session.exec(select(WateringEvent).where(WateringEvent.start_time >= since)).all()
        for w in watering:
            items.append(
                {
                    "type": "watering",
                    "title": f"Podlewanie: {w.zone_name}",
                    "start": w.start_time.isoformat(),
                    "end": w.end_time.isoformat() if w.end_time else None,
                    "duration_min": w.duration_min,
                }
            )

        mowing = session.exec(select(MowingEvent).where(MowingEvent.start_time >= since)).all()
        for m in mowing:
            items.append(
                {
                    "type": "mowing",
                    "title": "Koszenie",
                    "start": m.start_time.isoformat(),
                    "end": m.end_time.isoformat() if m.end_time else None,
                    "duration_min": m.duration_min,
                }
            )

        actions = session.exec(select(GardenAction).where(GardenAction.timestamp >= since)).all()
        for a in actions:
            items.append(
                {
                    "type": "action",
                    "title": f"{a.action_type}: {a.description or ''}".strip(": "),
                    "start": a.timestamp.isoformat(),
                    "end": None,
                    "photo_path": a.photo_path,
                }
            )

    items.sort(key=lambda x: x["start"], reverse=True)
    return items


@router.get("/weather/history")
def get_weather_history(days: int = 7) -> list[dict[str, Any]]:
    since = datetime.utcnow() - timedelta(days=days)
    with get_session() as session:
        rows = session.exec(
            select(WeatherSnapshot).where(WeatherSnapshot.timestamp >= since).order_by(WeatherSnapshot.timestamp)
        ).all()
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "temperature_c": r.temperature_c,
                "precipitation_mm": r.precipitation_mm,
                "humidity_pct": r.humidity_pct,
            }
            for r in rows
        ]


@router.get("/weather/forecast")
async def get_weather_forecast() -> dict[str, Any]:
    client = WeatherClient()
    return await client.get_current_and_forecast()


@router.post("/analysis")
async def get_analysis(days: int = 14) -> dict[str, Any]:
    """
    Wnioski AI na żądanie (przycisk w dashboardzie) - ALE zawsze zapisywane do
    tabeli Insight, tak samo jak wnioski generowane automatycznie przez
    scheduler (raz na 24h, patrz scheduler.py:poll_insights). Dzięki temu
    "wnioski" to narastająca historia oparta na zebranych danych, a nie tylko
    jednorazowa odpowiedź wyświetlana i zapominana.
    """
    insight = await generate_and_store_insight(days=days, triggered_by="manual")
    if insight is None:
        return {"error": "GEMINI_API_KEY nie jest ustawiony w .env - dodaj klucz z https://aistudio.google.com/apikey"}
    return {"analysis": insight.summary_text, "timestamp": insight.timestamp.isoformat()}


@router.get("/insights")
def list_insights(limit: int = 20) -> list[dict[str, Any]]:
    """Historia wszystkich wygenerowanych wniosków (automatycznych i ręcznych)."""
    with get_session() as session:
        rows = session.exec(select(Insight).order_by(Insight.timestamp.desc()).limit(limit)).all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "period_days": r.period_days,
                "summary_text": r.summary_text,
                "triggered_by": r.triggered_by,
            }
            for r in rows
        ]
