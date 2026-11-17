# Prognozy: bot do konkursów Metaculus

Bot sam bierze udział w konkursach botów AI na Metaculus (FutureEval co 4 miesiące, MiniBench co 2 tygodnie):

1. pobiera otwarte pytania,
2. szuka informacji z kilku źródeł naraz (wiadomości, wyszukiwarka, notowania Polymarket i Manifold),
3. robi 5 niezależnych prognoz (jednym modelem albo zespołem kilku) i bierze medianę,
4. sprawdza prognozę bezpiecznikami i wysyła ją z komentarzem-uzasadnieniem,
5. pilnuje dziennego limitu wydatków i daje znać mailem, gdy przestanie działać.

Działa jako **osobna usługa** na VPS: ma własnego użytkownika (`prognozy`), własny katalog (`/opt/prognozy`), własne klucze (`/etc/prognozy/prognozy.env`) i własny stan (`/var/lib/prognozy`). Nie korzysta z niczego, czego używają inne usługi na serwerze (np. Numerai), i nic im nie udostępnia.

## Dokumenty

| Plik | Co zawiera |
|---|---|
| [docs/REJESTRACJA.md](docs/REJESTRACJA.md) | Co właściciel zakłada na Metaculus, krok po kroku |
| [docs/WDROZENIE.md](docs/WDROZENIE.md) | Instalacja na VPS, pierwsze uruchomienie, logi, aktualizacja |
| [docs/ZASADY.md](docs/ZASADY.md) | Zasady konkursu, których bot i właściciel muszą pilnować |
| [docs/PLAN.md](docs/PLAN.md) | Co jest zrobione i kolejne ulepszenia |

## Jak to jest zbudowane

Bot stoi na oficjalnej bibliotece Metaculus [`forecasting-tools`](https://github.com/Metaculus/forecasting-tools) (licencja MIT). Biblioteka odpowiada za klienta API, modele pytań i budowę rozkładów liczbowych. Nasz kod to:

| Moduł | Rola |
|---|---|
| `src/prognozy/bot.py` | Prompty i prognozy dla pytań binarnych, wielokrotnego wyboru, liczbowych i dat |
| `src/prognozy/research.py` | Wyszukiwanie z kilku źródeł równolegle (AskNews + model wyszukujący). Gdy żadne główne źródło nie odpowie, pytanie jest pomijane |
| `src/prognozy/markets.py` | Notowania Polymarket i Manifold (źródło dodatkowe, bez kluczy) |
| `src/prognozy/ops.py` | Powiadomienia healthchecks.io i dzienny limit wydatków OpenRouter |
| `src/prognozy/compare.py` | Porównanie modeli na otwartych pytaniach spoza turniejów, względem prognozy społeczności |
| `src/prognozy/guards.py` | Bezpieczniki: komentarz obowiązkowy, zakres binarny 1–99%, poprawne opcje, rosnąca CDF z właściwymi granicami |
| `src/prognozy/ledger.py` | Rejestr wysłanych prognoz (SQLite), który chroni przed dublami i pozwala dosłać brakujący komentarz |
| `src/prognozy/publisher.py` | Wysyłka: najpierw bezpieczniki i rejestr, dopiero potem Metaculus |
| `src/prognozy/runner.py` | Jedno przejście: turnieje, wybór pytań, prognozy, wysyłka |
| `src/prognozy/cli.py` | Polecenie `prognozy check` / `prognozy run` |
| `deploy/` | Usługa i timer systemd, instalator, wzór pliku z kluczami |

## Szybki start lokalnie

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock pytest && pip install --no-deps -e .
pytest                       # testy offline, bez kluczy i bez sieci
prognozy check               # pokazuje, czego brakuje w konfiguracji
```

Z kluczami w środowisku:

```bash
prognozy run --mode test --dry-run      # pytania testowe, nic nie wysyła
prognozy run --mode test --publish      # wysyła na pytania testowe (bot-testing-area)
prognozy run --mode minibench --publish
prognozy run --mode tournament --publish  # główny turniej + MiniBench
prognozy porownaj --modele model_a,model_b,model_a+model_b --pytania 30
```

Wersje wszystkich bibliotek są przypięte w `requirements.lock`; `pyproject.toml` podaje tylko dozwolone zakresy.

**Domyślnie bot niczego nie wysyła.** Wysyłanie włącza `--publish` albo `PROGNOZY_PUBLISH=true`.

## Ustawienia (zmienne środowiskowe)

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `METACULUS_TOKEN` | brak (wymagane) | Token konta bota |
| `OPENROUTER_API_KEY` | brak (wymagane*) | Klucz do modeli; *albo `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |
| `ASKNEWS_API_KEY` | brak | Drugie źródło wiadomości (zalecane; starsze konta: `ASKNEWS_CLIENT_ID` + `ASKNEWS_SECRET`) |
| `PROGNOZY_PUBLISH` | `false` | Czy wysyłać prognozy |
| `PROGNOZY_PREDICTIONS` | `5` | Ile prognoz na pytanie (mediana) |
| `PROGNOZY_SEARCH_MODELS` | `openrouter/perplexity/sonar-pro` | Modele wyszukujące, po przecinku |
| `PROGNOZY_MARKETS` | `true` | Notowania Polymarket/Manifold |
| `PROGNOZY_FORECAST_MODELS` | brak | Zespół modeli do prognozy, po przecinku |
| `PROGNOZY_HEALTHCHECK_URL` | brak | Adres pingu healthchecks.io |
| `PROGNOZY_DAILY_BUDGET_USD` | brak | Dzienny limit wydatków OpenRouter w $ |
| `PROGNOZY_BATCH_SIZE` | `5` | Co ile pytań sprawdzać budżet |
| `PROGNOZY_MODEL_DEFAULT` | wg biblioteki | Model końcowej prognozy |
| `PROGNOZY_MODEL_PARSER` | wg biblioteki | Model odczytujący liczby z odpowiedzi |
| `PROGNOZY_TOURNAMENT`, `PROGNOZY_MINIBENCH` | wg biblioteki | ID turniejów (na nowy sezon) |
| `PROGNOZY_STATE_DIR` | `./stan` | Katalog rejestru (na VPS `/var/lib/prognozy`) |

Klucze są tylko w zmiennych środowiskowych. W logach ich wartości są zastępowane `***`.
