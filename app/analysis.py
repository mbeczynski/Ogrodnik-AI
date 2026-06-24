"""
Wspólna logika budowania podsumowania danych i generowania wniosków AI.
Używana zarówno przez scheduler (automatyczne, okresowe wnioski) jak i przez
endpoint /api/analysis (wnioski na żądanie) - obie ścieżki zapisują wynik do
tabeli Insight, żeby budować historię, a nie tylko jednorazową odpowiedź.
"""

import logging
from datetime import datetime, timedelta

from sqlmodel import select

from .db import get_session
from .integrations.gemini import GeminiClient
from .models import GardenAction, Insight, MowingEvent, WateringEvent, WeatherSnapshot

logger = logging.getLogger("ogrodnik.analysis")


def build_data_summary(days: int = 14) -> str:
    """Zwraca tekstowe podsumowanie zebranych danych z ostatnich `days` dni."""
    since = datetime.utcnow() - timedelta(days=days)
    lines = [f"Dane z ostatnich {days} dni (od {since.date()}):", ""]

    with get_session() as session:
        watering = session.exec(select(WateringEvent).where(WateringEvent.start_time >= since)).all()
        lines.append(f"Podlewania ({len(watering)}):")
        for w in watering[-20:]:
            lines.append(
                f"- {w.start_time:%Y-%m-%d %H:%M} strefa '{w.zone_name}', "
                f"czas trwania: {w.duration_min or '?'} min"
            )

        mowing = session.exec(select(MowingEvent).where(MowingEvent.start_time >= since)).all()
        lines.append(f"\nKoszenia ({len(mowing)}):")
        for m in mowing[-20:]:
            lines.append(f"- {m.start_time:%Y-%m-%d %H:%M}, czas trwania: {m.duration_min or '?'} min")

        weather = session.exec(
            select(WeatherSnapshot).where(WeatherSnapshot.timestamp >= since).order_by(WeatherSnapshot.timestamp)
        ).all()
        total_precip = sum(w.precipitation_mm or 0 for w in weather)
        lines.append(f"\nPogoda: {len(weather)} pomiarów, suma opadów ~{total_precip:.1f} mm.")

        actions = session.exec(select(GardenAction).where(GardenAction.timestamp >= since)).all()
        lines.append(f"\nRęczne akcje ogrodowe ({len(actions)}):")
        for a in actions:
            detail = f" produkt: {a.product}" if a.product else ""
            detail += f" dawka: {a.amount}" if a.amount else ""
            lines.append(f"- {a.timestamp:%Y-%m-%d} [{a.action_type}] {a.description or ''}{detail}")

    return "\n".join(lines)


async def generate_and_store_insight(days: int = 14, triggered_by: str = "scheduler") -> Insight | None:
    """Generuje wnioski Gemini na podstawie zebranych danych i zapisuje je w bazie."""
    client = GeminiClient()
    if not client.configured:
        logger.info("Gemini nieskonfigurowany (brak GEMINI_API_KEY) - pomijam generowanie wniosków")
        return None

    summary = build_data_summary(days=days)
    try:
        text = await client.analyze(summary)
    except Exception:
        logger.exception("Błąd podczas generowania wniosków Gemini")
        return None

    with get_session() as session:
        insight = Insight(period_days=days, summary_text=text, triggered_by=triggered_by)
        session.add(insight)
        session.commit()
        session.refresh(insight)
        return insight


def get_latest_insight() -> Insight | None:
    with get_session() as session:
        return session.exec(select(Insight).order_by(Insight.timestamp.desc())).first()
