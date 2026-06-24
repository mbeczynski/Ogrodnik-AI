"""
Integracja z kosiarką Dreame A1/A1 Pro.

Dreame nie ma oficjalnego publicznego API. Ta klasa jest cienką warstwą
abstrakcji, żeby reszta aplikacji nie musiała wiedzieć, skąd biorą się dane.

Domyślna implementacja: most przez Home Assistant (REST API), zakładając że
masz w HA działającą custom-integrację kosiarki Dreame (np. projekty
bhuebschen/dreame-mower lub nzben/dreame-mower-better - patrz ARCHITECTURE.md).

Jeśli nie masz Home Assistant skonfigurowanego (HA_BASE_URL / HA_LONG_LIVED_TOKEN
puste w .env), klient działa w trybie "mock" i zwraca brak danych - żeby reszta
aplikacji (dashboard, baza) działała i dała się przetestować już teraz.
"""

from datetime import datetime
from typing import Any

import httpx

from .. import runtime_settings as rs


class DreameClient:
    def __init__(self):
        self.ha_base_url = rs.get_value("ha_base_url")
        self.ha_token = rs.get_value("ha_long_lived_token")
        self.entity_id = rs.get_value("ha_mower_entity_id")

    @property
    def configured(self) -> bool:
        return bool(self.ha_base_url and self.ha_token and self.entity_id)

    async def get_mower_state(self) -> dict[str, Any] | None:
        """Pobiera aktualny stan encji kosiarki z Home Assistant."""
        if not self.configured:
            return None
        headers = {"Authorization": f"Bearer {self.ha_token}"}
        url = f"{self.ha_base_url}/api/states/{self.entity_id}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def get_recent_history(self, since: datetime) -> list[dict[str, Any]]:
        """Pobiera historię stanów encji od `since` (Home Assistant History API)."""
        if not self.configured:
            return []
        headers = {"Authorization": f"Bearer {self.ha_token}"}
        url = f"{self.ha_base_url}/api/history/period/{since.isoformat()}"
        params = {"filter_entity_id": self.entity_id}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else []

    @staticmethod
    def state_to_session_guess(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Bardzo prosta heurystyka: traktuje ciągłe odcinki stanu "cleaning"/"mowing"
        jako jedną sesję koszenia. Do dopracowania pod konkretne nazwy stanów
        zwracane przez Twoją integrację Dreame w HA.
        """
        sessions = []
        current_start = None
        mowing_states = {"cleaning", "mowing", "on"}
        for state in states:
            is_mowing = state.get("state") in mowing_states
            if is_mowing and current_start is None:
                current_start = state.get("last_changed")
            elif not is_mowing and current_start is not None:
                sessions.append({"start_time": current_start, "end_time": state.get("last_changed")})
                current_start = None
        return sessions
