"""
Klient do Gemini API (Google AI Studio) - używany do:
1) analizy zebranych danych ogrodowych (podlewanie, koszenie, pogoda, log akcji),
2) rozpoznawania roślin na zdjęciach (wejście multimodalne) do mapy ogrodu.

Klucz API: https://aistudio.google.com/apikey. Klucz i model można ustawić w
.env (GEMINI_API_KEY/GEMINI_MODEL) ALBO w aplikacji w zakładce "Ustawienia" -
patrz app/runtime_settings.py (wartość z ustawień w UI ma priorytet nad .env).

Endpoint REST (bez dodatkowego SDK, zgodnie z resztą integracji w tym projekcie):
https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
"""

import json
import re
from base64 import b64encode
from typing import Any

import httpx

from .. import runtime_settings as rs

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

ANALYSIS_SYSTEM_PROMPT = (
    "Jesteś asystentem ogrodniczym analizującym dane z czujników i logów ogrodu "
    "(nawadnianie Hunter Hydrawise, koszenie Dreame, pogoda, ręczny log akcji takich "
    "jak nawożenie). Na podstawie podanych danych podaj krótką (max 8 punktów), "
    "konkretną analizę po polsku: co wygląda dobrze, co wygląda niepokojąco lub "
    "nieoptymalnie (np. podlewanie mimo deszczu, zbyt rzadkie/częste koszenie, dawno "
    "nienawożony trawnik) oraz 2-3 konkretne rekomendacje na następne dni."
)

PLANT_ID_PROMPT = (
    "Jesteś botanikiem analizującym zdjęcie z ogrodu. Zidentyfikuj wszystkie rośliny "
    "widoczne na zdjęciu. Odpowiedz WYŁĄCZNIE poprawnym JSON-em (bez markdown, bez "
    "```), w formacie: "
    "[{\"name\": \"polska nazwa zwyczajowa\", \"scientific_name\": \"nazwa łacińska albo null\", "
    "\"notes\": \"krótka uwaga, np. stan zdrowia, pozycja na zdjęciu (lewo/środek/prawo, "
    "przód/tył)\"}]. Jeśli nie rozpoznajesz żadnej rośliny, zwróć []."
)


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or rs.get_value("gemini_api_key")
        self.model = model or rs.get_value("gemini_model") or "gemini-2.5-flash"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _require_key(self) -> str:
        if not self.configured:
            raise RuntimeError(
                "GEMINI_API_KEY nie jest ustawiony - dodaj go w Ustawieniach albo w .env"
            )
        return self.api_key

    async def _generate(self, parts: list[dict[str, Any]], system_prompt: str, max_tokens: int = 800) -> str:
        url = f"{BASE_URL}/{self.model}:generateContent"
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
        }
        headers = {"x-goog-api-key": self._require_key(), "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()

        try:
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return "Gemini nie zwrócił treści odpowiedzi (sprawdź surową odpowiedź API)."

    async def analyze(self, data_summary: str) -> str:
        """Analiza tekstowych danych ogrodowych -> wnioski i rekomendacje (tekst)."""
        return await self._generate([{"text": data_summary}], ANALYSIS_SYSTEM_PROMPT)

    async def identify_plants(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> list[dict[str, Any]]:
        """
        Wysyła zdjęcie do Gemini (multimodal) i prosi o listę rozpoznanych roślin
        w formacie JSON. Zwraca listę dict-ów {name, scientific_name, notes}.
        Jeśli model nie zwrócił poprawnego JSON-a, zwraca jeden wpis z surowym
        tekstem w polu "notes", żeby nic nie zgubić.
        """
        parts = [
            {"inlineData": {"mimeType": mime_type, "data": b64encode(image_bytes).decode("ascii")}},
            {"text": "Zidentyfikuj rośliny na tym zdjęciu ogrodu."},
        ]
        text = await self._generate(parts, PLANT_ID_PROMPT, max_tokens=1000)

        cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return [{"name": "Nie udało się rozpoznać automatycznie", "scientific_name": None, "notes": text}]
