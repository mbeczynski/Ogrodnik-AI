"""Zadania cykliczne: pollowanie Hydrawise, Open-Meteo, Dreame/HA i generowanie wniosków AI."""

import json
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select

from . import runtime_settings as rs
from .analysis import generate_and_store_insight
from .config import settings
from .db import get_session
from .integrations.dreame import DreameClient
from .integrations.hydrawise import HydrawiseClient
from .integrations.weather import WeatherClient
from .models import MowingEvent, WateringEvent, WeatherSnapshot

logger = logging.getLogger("ogrodnik.scheduler")

# Strefy aktualnie w trakcie biegu (relay_id -> WateringEvent.id), żeby wykryć koniec
_active_runs: dict[int, int] = {}


def _parse_ha_timestamp(value: str) -> datetime:
    """Home Assistant zwraca znaczniki czasu z offsetem (np. +00:00). Resztę
    aplikacji trzymamy w naiwnym UTC (datetime.utcnow()), więc normalizujemy
    tutaj, żeby porównania w bazie (SQLite) były konsystentne."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


async def poll_weather() -> None:
    try:
        client = WeatherClient()
        data = await client.get_current_and_forecast()
        snap = client.extract_current_snapshot(data)
        if not snap.get("timestamp"):
            return
        with get_session() as session:
            session.add(
                WeatherSnapshot(
                    timestamp=datetime.fromisoformat(snap["timestamp"]),
                    temperature_c=snap.get("temperature_c"),
                    precipitation_mm=snap.get("precipitation_mm"),
                    humidity_pct=snap.get("humidity_pct"),
                    wind_kph=snap.get("wind_kph"),
                )
            )
            session.commit()
        logger.info("Zapisano snapshot pogody: %s", snap)
    except Exception:
        logger.exception("Błąd podczas pollowania pogody")


async def poll_hydrawise() -> None:
    if not rs.get_value("hydrawise_api_key"):
        return
    try:
        client = HydrawiseClient()
        status = await client.get_status_schedule()
        active = client.parse_active_relays(status)
        active_relay_ids = {r["relay_id"] for r in active}

        with get_session() as session:
            # Nowe biegi, które właśnie wykryliśmy
            for relay in active:
                if relay["relay_id"] not in _active_runs:
                    event = WateringEvent(
                        relay_id=relay["relay_id"],
                        zone_name=relay["name"] or f"Zone {relay['relay_id']}",
                        start_time=datetime.utcnow(),
                        raw_payload=json.dumps(relay["raw"]),
                    )
                    session.add(event)
                    session.commit()
                    _active_runs[relay["relay_id"]] = event.id

            # Biegi, które się zakończyły od ostatniego sprawdzenia
            finished = [rid for rid in _active_runs if rid not in active_relay_ids]
            for rid in finished:
                event_id = _active_runs.pop(rid)
                event = session.get(WateringEvent, event_id)
                if event and event.end_time is None:
                    event.end_time = datetime.utcnow()
                    event.duration_min = (event.end_time - event.start_time).total_seconds() / 60
                    session.add(event)
                    session.commit()
        logger.info("Hydrawise: %d aktywnych stref", len(active))
    except Exception:
        logger.exception("Błąd podczas pollowania Hydrawise")


async def poll_dreame() -> None:
    """
    Zaciąga historię stanu kosiarki z Home Assistant i zapisuje wykryte sesje
    koszenia do naszej własnej bazy (MowingEvent). To jest istotne, bo recorder
    Home Assistanta domyślnie trzyma historię tylko ~10 dni - nasza baza ma
    trzymać to dłużej, do analizy trendów.
    """
    client = DreameClient()
    if not client.configured:
        return
    try:
        with get_session() as session:
            last_event = session.exec(select(MowingEvent).order_by(MowingEvent.start_time.desc())).first()
            since = last_event.end_time if (last_event and last_event.end_time) else datetime.utcnow() - timedelta(days=7)

            states = await client.get_recent_history(since=since)
            sessions = client.state_to_session_guess(states)

            existing_starts = {
                e.start_time.isoformat()
                for e in session.exec(select(MowingEvent).where(MowingEvent.start_time >= since)).all()
            }

            saved = 0
            for s in sessions:
                if not s.get("end_time"):
                    continue  # sesja jeszcze w toku - dopiszemy ją po zakończeniu
                start_time = _parse_ha_timestamp(s["start_time"])
                if start_time.isoformat() in existing_starts:
                    continue
                end_time = _parse_ha_timestamp(s["end_time"])
                session.add(
                    MowingEvent(
                        start_time=start_time,
                        end_time=end_time,
                        duration_min=(end_time - start_time).total_seconds() / 60,
                        raw_payload=json.dumps(s),
                    )
                )
                saved += 1
            if saved:
                session.commit()
                logger.info("Dreame/HA: zapisano %d nowych sesji koszenia", saved)
    except Exception:
        logger.exception("Błąd podczas pollowania Dreame/Home Assistant")


async def poll_insights() -> None:
    """Okresowo (np. raz dziennie) generuje i zapisuje wnioski AI na podstawie
    danych zebranych do tej pory - nie tylko na żądanie z dashboardu."""
    try:
        insight = await generate_and_store_insight(days=14, triggered_by="scheduler")
        if insight:
            logger.info("Zapisano nowy automatyczny wniosek AI (id=%s)", insight.id)
    except Exception:
        logger.exception("Błąd podczas automatycznego generowania wniosków AI")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    minutes = settings.poll_interval_minutes
    scheduler.add_job(poll_weather, "interval", minutes=max(minutes, 15), id="poll_weather")
    scheduler.add_job(poll_hydrawise, "interval", minutes=minutes, id="poll_hydrawise")
    scheduler.add_job(poll_dreame, "interval", minutes=minutes, id="poll_dreame")
    # Wnioski AI generujemy rzadziej niż polling danych - raz na 24h wystarczy,
    # żeby budować historię trendów bez zużywania niepotrzebnie limitu Gemini API.
    # next_run_time=teraz, żeby pierwszy wniosek powstał wkrótce po starcie
    # aplikacji, a nie po 24h czekania.
    scheduler.add_job(
        poll_insights, "interval", hours=24, id="poll_insights", next_run_time=datetime.now()
    )
    return scheduler
