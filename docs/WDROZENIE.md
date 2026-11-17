# Wdrożenie na VPS

Bot działa jako osobna usługa systemd. Wszystko, czego używa:

| Co | Gdzie |
|---|---|
| Użytkownik systemowy | `prognozy` (bez powłoki, bez katalogu domowego) |
| Kod i środowisko Pythona | `/opt/prognozy` |
| Klucze | `/etc/prognozy/prognozy.env` (prawa 600, root) |
| Stan (rejestr wysłanych prognoz) | `/var/lib/prognozy` |
| Usługa i timer | `prognozy.service`, `prognozy.timer` |
| Logi | `journalctl -u prognozy` |

Nie dotyka katalogów, użytkowników, kluczy ani jednostek innych usług (np. Numerai). Usługa ma `ProtectSystem=strict` i `ProtectHome=yes`, więc i tak może pisać tylko do `/var/lib/prognozy`.

Wymagania: Debian/Ubuntu z systemd, `git`, Python 3.11–3.13 albo [`uv`](https://docs.astral.sh/uv/) (instalator sam pobierze wtedy Pythona 3.12).

## 1. Pobranie kodu

```bash
sudo git clone https://github.com/DarekTMA/Metaculus.git /root/prognozy-src
cd /root/prognozy-src
git checkout claude/osobne-repo-usluga-14m3a7   # dopóki zmiany nie są w main
```

Jeśli repozytorium jest prywatne, `git clone` zapyta o login. Najprościej: utwórz na GitHub osobny klucz tylko do odczytu tego repo („Deploy key”) i klonuj przez SSH. Nie używaj klucza ani tokenu, z którego korzystają inne usługi na serwerze.

## 2. Instalacja

```bash
sudo bash deploy/install.sh
```

Skrypt tworzy użytkownika, kopiuje kod do `/opt/prognozy`, instaluje zależności, tworzy pusty plik z kluczami i instaluje jednostki systemd. Timera **nie** włącza.

## 3. Klucze

```bash
sudo nano /etc/prognozy/prognozy.env
```

Wpisz `METACULUS_TOKEN`, `OPENROUTER_API_KEY` i (zalecane) `ASKNEWS_API_KEY`. Na razie zostaw `PROGNOZY_PUBLISH=false`.

```bash
sudo bash /opt/prognozy/deploy/run-once.sh check
```

Ma pokazać `OK` i co najmniej jedno źródło informacji (najlepiej dwa plus `prediction-markets`).

### Powiadomienia o awarii (5 minut, zalecane)

1. Załóż darmowe konto na https://healthchecks.io i dodaj nowy check („Add Check”).
2. Ustaw **Period: 20 minut** i **Grace: 1 godzina**. Mail przyjdzie, gdy bot przez ponad godzinę nie zgłosi udanego przejścia albo zgłosi błąd.
3. Skopiuj adres pingu (`https://hc-ping.com/…`) do `PROGNOZY_HEALTHCHECK_URL` w pliku z kluczami.

W treści pingu jest podsumowanie przejścia, więc w panelu healthchecks widać też, ile prognoz poszło.

### Limit wydatków

- `PROGNOZY_DAILY_BUDGET_USD` (domyślnie 5 $): przed każdą porcją 5 pytań bot pyta OpenRouter o dzisiejsze zużycie klucza i po przekroczeniu limitu kończy przejście. Pozostałe pytania wrócą następnego dnia.
- Limit w bocie może przekroczyć próg o koszt jednej porcji. Dlatego **ustaw też twardy limit na samym kluczu w panelu OpenRouter** (Settings → Keys → limit kredytów).

## 4. Próba na pytaniach testowych

```bash
# bez wysyłania: pokazuje w logu, co by poszło
sudo bash /opt/prognozy/deploy/run-once.sh run --mode test --dry-run

# z wysyłaniem na turniej testowy bot-testing-area (nie liczy się do rankingu)
sudo bash /opt/prognozy/deploy/run-once.sh run --mode test --publish
```

Potem na Metaculus: Ustawienia → My Forecasting Bots → „Switch to bot account” i sprawdź na pytaniu testowym, czy jest prognoza i prywatny komentarz.

Testowe pytania mają osobny rejestr (`rejestr-test.sqlite`), więc nie blokują prawdziwych.

## 5. Włączenie

```bash
sudo sed -i 's/^PROGNOZY_PUBLISH=.*/PROGNOZY_PUBLISH=true/' /etc/prognozy/prognozy.env
sudo systemctl enable --now prognozy.timer
systemctl list-timers prognozy.timer
```

Timer uruchamia jedno przejście co 20 minut (`--mode tournament`: główny turniej + MiniBench). Pytania już prognozowane są pomijane.

## Codzienna obsługa

```bash
journalctl -u prognozy -n 100          # ostatnie logi
journalctl -u prognozy -f              # na żywo
sudo systemctl start prognozy.service  # przejście teraz, poza kolejnością
sudo systemctl disable --now prognozy.timer   # pauza
```

Każde przejście kończy się w logu linią `Podsumowanie: wysłane=…, odrzucone=…, duble=…, błędy=…`.

- **odrzucone**: prognoza nie przeszła bezpieczników i nie została wysłana,
- **błędy**: np. żadne źródło nie odpowiedziało; pytanie wróci przy następnym przejściu.

**Uwaga na zasady:** logi pokazują, *czy* bot działa. Nie poprawiaj promptów ani ustawień na podstawie tego, co bot prognozuje na otwartych pytaniach turnieju (patrz ZASADY.md).

## Porównanie modeli (przed sezonem i po zmianach)

```bash
sudo bash /opt/prognozy/deploy/run-once.sh porownaj \
  --modele openrouter/openai/gpt-5.4,openrouter/anthropic/claude-opus-5.5,openrouter/openai/gpt-5.4+openrouter/anthropic/claude-opus-5.5 \
  --pytania 30
```

- Bot prognozuje (bez wysyłania) na otwartych pytaniach Metaculus **spoza turniejów botów** i porównuje się z prognozą społeczności. Pytania turniejowe są odfiltrowane, więc to nie łamie zasady „bez człowieka w pętli”.
- Wariant z `+` to zespół modeli. Research jest wspólny dla wszystkich wariantów, więc płacimy za niego raz.
- Koszt: mniej więcej liczba pytań × 5 prognoz × liczba wariantów wywołań modelu. Dla 30 pytań i 3 wariantów to zwykle kilka dolarów. Dzienny limit wydatków tu nie działa, więc pilnuj limitu na kluczu.
- Wynik: tabela w terminalu oraz plik `/var/lib/prognozy/porownania/porownanie-<data>.jsonl`. Najlepszy wariant wpisz do `PROGNOZY_FORECAST_MODELS` (zespół) albo `PROGNOZY_MODEL_DEFAULT` (jeden model).
- Różnice poniżej ok. 2 punktów przy 30 pytaniach to zwykle szum. Przy wątpliwościach uruchom ponownie na innych pytaniach (wybierane są losowo).

## Aktualizacja

```bash
cd /root/prognozy-src && sudo git pull
sudo bash deploy/install.sh        # klucze i rejestr zostają nietknięte
```

Wersje bibliotek są przypięte w `requirements.lock`, więc instalacja zawsze daje to samo, co przeszło testy.

### Nowy sezon (styczeń, maj, wrzesień)

ID nowego turnieju jest w bibliotece Metaculus `forecasting-tools`. Na komputerze z repo (albo w sesji z Claude):

```bash
uv pip compile pyproject.toml --universal --python-version 3.11 -o requirements.lock --upgrade-package forecasting-tools
pip install -r requirements.lock && pytest      # testy muszą przejść
git commit -am "Aktualizacja forecasting-tools na nowy sezon" && git push
```

Potem na serwerze `git pull` i `install.sh` jak wyżej. Jeśli nowej wersji biblioteki jeszcze nie ma, ustaw w pliku z kluczami `PROGNOZY_TOURNAMENT=<slug lub ID nowego turnieju>` i usuń tę linię po aktualizacji.

Na nowy sezon odnów też dostęp do AskNews i sprawdź na Discordzie Metaculus, czy nie zmieniły się zasady.

## Usunięcie

```bash
sudo systemctl disable --now prognozy.timer
sudo rm /etc/systemd/system/prognozy.{service,timer} && sudo systemctl daemon-reload
sudo rm -rf /opt/prognozy /etc/prognozy /var/lib/prognozy
sudo userdel prognozy
```
