# Ogrodnik AI — architektura POC

## 1. Cel

Jedna aplikacja (dashboard webowy), która zbiera w jednym miejscu wszystko co dzieje się w ogrodzie:

- nawadnianie (sterownik Hunter Hydrawise),
- koszenie (kosiarka Dreame A1/A1 Pro),
- pogoda w lokalizacji ogrodu,
- zdjęcia,
- ręczny log działań (nawożenie, sadzenie, opryski, przycinanie itd.).

Cel docelowy: korelować dane ("czy lało, zanim nawadnianie ruszyło?", "czy kosiarka kosiła zbyt często po deszczu?", "kiedy ostatnio nawoziłem ten trawnik?") i pokazać to na jednej osi czasu.

## 2. Źródła danych i integracje

### 2.1 Hunter Hydrawise (nawadnianie)

Hydrawise ma oficjalne REST API v1 (klucz API z konta, "My Account → Generate API Key"). Działa tylko dla kontrolerów Wi-Fi (HC/Pro-HC/HPC), bezpłatnie, ale tylko do użytku osobistego (ToS zakazuje użycia komercyjnego — wystarczy nam to w 100%).

Ograniczenie, które trzeba świadomie zaakceptować: **darmowe REST API v1 nie udostępnia historii podlewań** — `statusschedule.php` zwraca tylko *nadchodzący* harmonogram (czas do następnego uruchomienia strefy, aktualnie trwający bieg). Pełna historia jest dostępna tylko w płatnym GraphQL API v2 (OAuth, wymaga zgody handlowej Huntera).

**Rozwiązanie dla POC:** odpytujemy `statusschedule.php` co ok. 1–5 minut (zgodnie z polem `nextpoll`) i sami budujemy historię, zapisując moment startu/końca biegu strefy, gdy wykryjemy `time == 1` (bieg w toku) → koniec, gdy strefa znów ma `time > 1`. To wystarczy do POC; jeśli kontroler ma historyczne raporty w aplikacji Hydrawise, można je later dociągnąć ręcznym eksportem.

Endpointy używane:
- `statusschedule.php?api_key=...` — status stref, najbliższy bieg, czujniki deszczu/przepływu.
- `setzone.php?action=run|stop|suspend&relay_id=...` — opcjonalne sterowanie (nie wymagane na MVP, ale przydatne np. do automatycznego wstrzymania podlewania po dużym deszczu).

### 2.2 Dreame A1 / A1 Pro (kosiarka)

Dreame **nie ma oficjalnego publicznego API**. Istnieją dwie ścieżki, obie reverse-engineered przez community:

1. **Lokalny protokół MiIO** (jak w `python-miio` / projekcie `Tasshack/dreame-vacuum`) — wymaga IP urządzenia + tokenu wyciągniętego z konta Dreame/Mi Home. Najbardziej "własny" sposób, działa bez chmury, ale wymaga ręcznego wydobycia tokenu (proces bywa kapryśny, zależny od regionu/firmware).
2. **Mostek przez Home Assistant** — jeśli używasz (lub dołożysz) Home Assistant z custom-integracją (`bhuebschen/dreame-mower`, `nzben/dreame-mower-better` itp.), to HA już rozwiązuje uwierzytelnianie i wystawia encje (stan koszenia, bateria, historia sesji) przez stabilne REST/WebSocket API Home Assistanta. Ogrodnik AI wtedy nie musi w ogóle znać protokołu Dreame — woła HA.

**Rekomendacja na POC:** opcja 2 (Home Assistant jako "hub"), bo jest znacznie stabilniejsza i szybsza do wdrożenia. Kod ma warstwę abstrakcji `DreameClient`, żeby później dało się podłączyć opcję 1 bez zmiany resztę aplikacji.

Masz już Home Assistant lokalnie — to przyjęte podejście domyślne. Ważne ograniczenie, które właśnie dlatego adresujemy własną bazą danych (patrz §3): **recorder Home Assistanta domyślnie trzyma historię tylko ok. 10 dni**. Ogrodnik AI odpytuje HA REST API (`/api/history/period/...`) co `POLL_INTERVAL_MINUTES` i zapisuje wykryte sesje koszenia (`MowingEvent`) do własnej, trwałej bazy SQLite — dzięki temu dane nie wypadają po 10 dniach i można budować trendy długoterminowe (np. "ile razy kosiłem w czerwcu vs. w maju").

Wymagane w `.env`: `HA_BASE_URL`, `HA_LONG_LIVED_TOKEN` (Profil użytkownika HA → Long-Lived Access Tokens) i `HA_MOWER_ENTITY_ID` (entity_id encji kosiarki w Twojej instalacji HA, np. `vacuum.dreame_a1_mower`).

### 2.3 Pogoda

**Open-Meteo** — brak klucza API, limit 10 000 zapytań/dzień (free, non-commercial), rozdzielczość 1-2 km w Europie Środkowej, dane godzinowe: temperatura, opady, wilgotność, wiatr. Wystarczające do POC i prawdopodobnie do produkcji też.

Endpoint: `GET https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&hourly=temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m&timezone=auto`

### 2.4 Gemini AI — warstwa analizy

Surowe dane (podlewanie, koszenie, pogoda, ręczny log) same w sobie niewiele mówią — wartość jest w korelacji. Dodajemy warstwę analityczną: backend buduje tekstowe podsumowanie danych z ostatnich N dni i wysyła je do Gemini API (`gemini-2.5-flash`, REST `generateContent`, klucz z [Google AI Studio](https://aistudio.google.com/apikey)) z promptem proszącym o: co wygląda dobrze, co wygląda niepokojąco (np. podlewanie mimo zapowiadanego/odnotowanego deszczu, zbyt rzadkie koszenie, dawno nienawożony trawnik) i 2–3 konkretne rekomendacje na najbliższe dni.

Działa **automatycznie w tle** (scheduler odpytuje raz na 24h, patrz `scheduler.py:poll_insights`) ORAZ na żądanie (przycisk "Odśwież teraz" w dashboardzie) — obie ścieżki zapisują wynik do tabeli `Insight`, więc to nie jednorazowa odpowiedź, ale narastająca historia wniosków oparta na tym, co faktycznie zebraliśmy w bazie. Dashboard domyślnie pokazuje najnowszy zapisany wniosek, bez konieczności klikania.

Kolejny naturalny krok: wysyłka codziennego podsumowania mailem/push, albo dołączenie zdjęć do analizy (Gemini obsługuje multimodalny input — można przesłać zdjęcie trawnika i zapytać o jego stan).

### 2.5 Zdjęcia i log akcji ogrodowych

Brak zewnętrznego API — to dane własne użytkownika. Prosty formularz w dashboardzie: typ akcji (nawożenie / sadzenie / oprysk / przycinanie / inne), opis, użyty produkt i dawka, opcjonalne zdjęcie (upload), znacznik czasu, opcjonalnie strefa ogrodu.

## 3. Model danych (POC, SQLite)

| Tabela | Kluczowe pola |
|---|---|
| `watering_event` | zone_name, start_time, end_time, duration_min, source |
| `mowing_event` | start_time, end_time, duration_min, area_m2 (opcjonalnie), battery_start/end, source |
| `weather_snapshot` | timestamp, temperature_c, precipitation_mm, humidity_pct, wind_kph |
| `garden_action` | timestamp, action_type, description, product, amount, zone, photo_path |
| `insight` | timestamp, period_days, summary_text, triggered_by (`scheduler`/`manual`) |

Wszystkie tabele mają `source` (np. `hydrawise`, `dreame`, `manual`) i `raw_payload` (JSON) — żeby nic nie gubić przy zmianach API dostawców.

## 4. Architektura systemu

```
                     ┌────────────────────┐
                     │   Open-Meteo API   │
                     └─────────┬──────────┘
                               │ poll (co 30-60 min)
┌────────────────┐    ┌────────▼─────────┐    ┌──────────────────┐
│ Hydrawise REST  │───▶│                  │◀───│ Home Assistant /  │
│  API (polling)  │    │   Ogrodnik AI    │    │ Dreame (mostek)   │
└────────────────┘    │   backend         │    └──────────────────┘
                       │  (FastAPI +       │
   ┌───────────────┐   │   APScheduler +   │
   │ Formularz akcji│──▶│   SQLite)         │
   │ + upload zdjęć │   │                  │
   └───────────────┘    └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │  Dashboard web    │
                         │ (Jinja2 + Chart.js)│
                         └───────────────────┘
```

Wszystko działa jako jeden proces (FastAPI), idealne na Raspberry Pi / mały VPS / kontener Docker w sieci domowej — żadna z integracji nie wymaga publicznego adresu IP (poza tym, że backend musi mieć wychodzący dostęp do internetu, by pollować Hydrawise i Open-Meteo).

## 5. Stack technologiczny (POC)

- **Backend:** Python 3.11+, FastAPI, SQLModel (SQLite), APScheduler (zadania cykliczne), httpx (klient HTTP).
- **Frontend:** Jinja2 server-side templates + Chart.js (CDN) — bez budowania SPA na etapie POC; jeśli projekt się rozrośnie, naturalna ścieżka to wydzielenie API i frontend w React/Vue.
- **Baza danych:** SQLite na start (zero-config), łatwa migracja do Postgres później.
- **Wdrożenie:** Docker Compose, działa lokalnie w sieci domowej (Raspberry Pi 4/5 wystarczy).

## 6. Plan POC (kolejność wdrażania)

1. Szkielet FastAPI + SQLite + model danych (gotowe w tym repo).
2. Integracja Open-Meteo (najprostsza, brak auth) — działa od razu po wpisaniu współrzędnych.
3. Integracja Hydrawise (wymaga klucza API z konta Hydrawise).
4. Formularz "dodaj akcję ogrodową" + upload zdjęć (działa bez żadnych zewnętrznych integracji).
5. Dashboard: jedna osia czasu łącząca wszystkie zdarzenia + wykres opady vs. podlewanie.
6. Integracja Dreame przez Home Assistant (wymaga działającego HA z custom-integracją kosiarki).
7. (Opcjonalnie, później) automatyzacje: np. „jeśli prognoza opadów > X mm w ciągu 24h, wstrzymaj najbliższe podlewanie” przez `setzone.php?action=suspend`.

## 7. Ryzyka i otwarte pytania

- Hydrawise free API nie ma historii — jeśli to okaże się zbyt ograniczające, jedyna droga to płatne API v2 (kontakt z Hunterem) albo budowanie własnej historii przez ciągły polling (przyjęte podejście).
- Integracja Dreame jest nieoficjalna (community, może się zepsuć po aktualizacji firmware/appki Dreame) — traktować jako "best effort", nie jako gwarantowaną.
- Jeśli nie masz jeszcze Home Assistant, trzeba go postawić (Raspberry Pi/Docker) zanim integracja z kosiarką zadziała — to jednorazowy koszt wdrożenia, ale wart tego ze względu na stabilność.
- ToS Huntera: użycie czysto osobiste, nie komercyjne — zgodne z tym projektem.
