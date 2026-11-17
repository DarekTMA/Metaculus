# Plan

## Zrobione

**Wersja 0.1**
- Bot na oficjalnej bibliotece Metaculus: pytania binarne, wielokrotnego wyboru, liczbowe, dyskretne i daty. Pytania warunkowe są na razie pomijane.
- Wyszukiwanie z 2 źródeł równolegle (AskNews + Perplexity Sonar przez OpenRouter).
- 5 prognoz na pytanie, mediana. Bez sztucznego przesuwania do skrajności.
- Pełny kontekst pytania w promptach: tło, warunki rozstrzygnięcia, drobny druk.
- Bezpieczniki, rejestr anty-duble, dosyłanie komentarzy, maskowanie kluczy.
- Usługa systemd z timerem co 20 minut, instalator, testy offline w CI.

**Wersja 0.2**
- Notowania Polymarket i Manifold pobierane wprost z ich API (źródło dodatkowe; samo nie wystarcza do prognozy).
- Zespół modeli: `PROGNOZY_FORECAST_MODELS`, nazwa modelu przy każdym uzasadnieniu w komentarzu.
- `prognozy porownaj`: porównanie wariantów na pytaniach spoza turniejów, względem prognozy społeczności.
- Powiadomienia o awarii (healthchecks.io) i dzienny limit wydatków (odczyt z OpenRouter).
- Przypięte wersje bibliotek (`requirements.lock`), używane przez instalator i CI.

## Harmonogram

- **Teraz (jesień 2026):** rejestracja, wdrożenie, próba na pytaniach testowych, potem MiniBench i resztka sezonu jesiennego. Bez oczekiwań co do nagród.
- **Grudzień 2026:** `prognozy porownaj` na 2–3 wariantach modeli, wybór najlepszego.
- **Początek stycznia 2027:** sezon wiosenny, właściwy cel. Aktualizacja biblioteki (ID turnieju), odnowienie AskNews.

## Do decyzji właściciela

- **Otwarty kod.** Daje mniej więcej podwójne kredyty i pewną kwalifikację do nagród. Wymaga dodania licencji (np. MIT) i upublicznienia repo. W repo nie ma kluczy ani danych właściciela.

## Dalsze możliwe ulepszenia

1. Trzecie źródło: przeglądanie stron (np. Exa/SmartSearcher) dla pytań wymagających danych z konkretnych serwisów.
2. Pytania warunkowe, jeśli pojawią się w turnieju.
3. Market Pulse (ciągła aktualizacja prognoz liczbowych): wymaga ponownego prognozowania, czego bot teraz celowo nie robi.
4. Porównanie także na pytaniach liczbowych (dziś `porownaj` obsługuje tylko binarne).
