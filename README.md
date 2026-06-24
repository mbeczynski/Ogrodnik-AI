# 🌱 Ogrodnik AI

Webowy dashboard ogrodowy, który łączy w jednym miejscu:

- **nawadnianie** — Hunter Hydrawise (Wi-Fi),
- **koszenie** — robot Dreame (przez most Home Assistant),
- **pogodę** dla lokalizacji ogrodu (Open-Meteo, bez klucza API),
- **ręczny log działań** (nawożenie, sadzenie, przycinanie, ochrona roślin) ze zdjęciami,
- **mapę ogrodu** z rozmieszczeniem roślin (pinezki na zdjęciu/szkicu),
- **analizę AI** (Gemini) — wnioski i rekomendacje generowane automatycznie co 24h
  oraz na żądanie, a także rozpoznawanie roślin ze zdjęcia.

Wszystkie zebrane dane trzymane są we własnej bazie SQLite, bo domyślny rekorder
Home Assistant przechowuje historię tylko ~10 dni.

Pełny opis architektury i decyzji projektowych: [ARCHITECTURE.md](./ARCHITECTURE.md).

## Funkcje

| Obszar | Co robi |
|---|---|
| Dashboard | Podsumowanie podlewań, koszeń, pogody i najnowszych wniosków AI |
| Hunter Hydrawise | Polling harmonogramu, budowanie lokalnej historii podlewań |
| Dreame (kosiarka) | Historia koszeń przez Home Assistant (REST API) |
| Pogoda | Aktualne dane i prognoza dla współrzędnych ogrodu (Open-Meteo) |
| Log akcji | Formularz + zdjęcia dla nawożenia, sadzenia, przycinania itd. |
| Mapa ogrodu | Wgraj zdjęcie/szkic, klikaj pozycje, dodawaj rośliny jako pinezki |
| AI rozpoznawanie roślin | Wgraj zdjęcie z ogrodu, Gemini Vision proponuje gatunki do mapy |
| Analiza AI | Automatyczne wnioski co 24h + analiza na żądanie, historia wniosków |
| Ustawienia w UI | Klucze API i parametry edytowalne z aplikacji, bez restartu kontenera |

## Szybki start (Docker — zalecane)

```bash
git clone <adres-twojego-repo> ogrodnik-ai
cd ogrodnik-ai

cp .env.example .env
# .env możesz zostawić w większości puste — wszystkie klucze API da się
# wpisać później w aplikacji, w zakładce "Ustawienia"

docker compose up -d --build
```

Otwórz http://localhost:8000

Dane (baza SQLite, zdjęcia, mapy) trzymane są w wolumenie Dockera `ogrodnik_data`,
więc przetrwają restart i rebuild kontenera.

## Szybki start (lokalnie, bez Dockera)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env

uvicorn app.main:app --reload
```

Otwórz http://localhost:8000

## Konfiguracja kluczy API

Klucze (Hydrawise, Home Assistant, Gemini) można ustawić dwoma sposobami:

1. **W aplikacji** — zakładka *Ustawienia* (`/settings`). Wartość zapisana tu ma
   priorytet nad `.env` i działa od razu, bez restartu kontenera — wygodne przy
   Dockerze.
2. **W `.env`** — przed pierwszym startem, patrz [`.env.example`](./.env.example).

Aplikacja działa od razu (bez żadnych kluczy) dla: dashboardu, formularza akcji
ogrodowych ze zdjęciami, mapy ogrodu i pogody (Open-Meteo nie wymaga klucza).
Hydrawise, Dreame/Home Assistant i Gemini AI aktywują się automatycznie po
uzupełnieniu odpowiednich danych.

## Status integracji

| Integracja | Wymaga | Status w POC |
|---|---|---|
| Open-Meteo (pogoda) | nic | działa od razu |
| Log akcji + zdjęcia | nic | działa od razu |
| Mapa ogrodu (rośliny) | nic | działa od razu |
| Hunter Hydrawise | API key | działa (polling, historia budowana lokalnie) |
| Dreame (kosiarka) | Home Assistant + integracja kosiarki | szkielet gotowy, wymaga skonfigurowanego HA |
| Gemini AI (analiza + rozpoznawanie roślin) | API key z [aistudio.google.com](https://aistudio.google.com/apikey) | działa (automatycznie co 24h + na żądanie) |

## Stack technologiczny

FastAPI + Jinja2 (server-rendered, bez SPA) · SQLModel/SQLite · APScheduler ·
httpx · Tailwind CSS i Chart.js z CDN · Docker / docker-compose.

## Licencja

[MIT](./LICENSE) — używaj, modyfikuj i rozwijaj swobodnie.
