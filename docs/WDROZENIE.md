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

Wpisz `METACULUS_TOKEN`, `OPENROUTER_API_KEY` i (zalecane) `ASKNEWS_CLIENT_ID` / `ASKNEWS_SECRET`. Na razie zostaw `PROGNOZY_PUBLISH=false`.

```bash
sudo bash /opt/prognozy/deploy/run-once.sh check
```

Ma pokazać `OK` i co najmniej jedno źródło informacji (najlepiej dwa).

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

## Aktualizacja

```bash
cd /root/prognozy-src && sudo git pull
sudo bash deploy/install.sh        # klucze i rejestr zostają nietknięte
```

Na początku sezonu (styczeń, maj, wrzesień) zaktualizuj też bibliotekę Metaculus, bo w niej są ID nowych turniejów:

```bash
sudo /opt/prognozy/.venv/bin/pip install --upgrade "forecasting-tools<0.4"
```

Jeśli nowej wersji jeszcze nie ma, ustaw w pliku z kluczami `PROGNOZY_TOURNAMENT=<slug lub ID nowego turnieju>`.

## Usunięcie

```bash
sudo systemctl disable --now prognozy.timer
sudo rm /etc/systemd/system/prognozy.{service,timer} && sudo systemctl daemon-reload
sudo rm -rf /opt/prognozy /etc/prognozy /var/lib/prognozy
sudo userdel prognozy
```
