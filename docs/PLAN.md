# Plan

## Zrobione (wersja 0.1)

- Bot na oficjalnej bibliotece Metaculus: pytania binarne, wielokrotnego wyboru, liczbowe, dyskretne i daty. Pytania warunkowe są na razie pomijane.
- Wyszukiwanie z 2 źródeł równolegle (AskNews + Perplexity Sonar przez OpenRouter); prompt prosi też o notowania rynków prognoz i podobne pytania.
- 5 prognoz na pytanie, mediana. Bez sztucznego przesuwania do skrajności.
- Pełny kontekst pytania w promptach: tło, warunki rozstrzygnięcia, drobny druk.
- Bezpieczniki, rejestr anty-duble, dosyłanie komentarzy, maskowanie kluczy.
- Usługa systemd z timerem co 20 minut, instalator, testy offline w CI.

## Harmonogram

- **Teraz (jesień 2026):** uruchomić na MiniBench i resztce sezonu jesiennego. Bez oczekiwań co do nagród; to sprawdzian i podstawa do większych kredytów.
- **Początek stycznia 2027:** sezon wiosenny, właściwy cel. Przed startem: aktualizacja biblioteki (ID turnieju), odnowienie AskNews.

## Kolejne ulepszenia (w tej kolejności)

1. **Mocniejszy model końcowej prognozy.** W ankietach najsilniej z wynikiem korelował GPT-5.4. Ustawienie: `PROGNOZY_MODEL_DEFAULT`. Wybór modelu sprawdzić na pytaniach zamkniętych, nie na otwartych.
2. **Lepsze wyszukiwanie:** przeglądanie stron (np. Exa/SmartSearcher) jako trzecie źródło.
3. **Rynki i podobne pytania wprost:** pobieranie notowań z API Polymarket/Manifold zamiast liczenia na to, że znajdzie je wyszukiwarka.
4. **Uśrednianie kilku modeli** (np. 2–3 różne modele po 2 prognozy) zamiast 5 prognoz jednego modelu.
5. **Ocena wsteczna** na pytaniach rozstrzygniętych (np. narzędzie `metaculus-bot-review`), żeby porównywać zmiany bez naruszania zasady „bez człowieka w pętli”.
6. Opcjonalnie: **Market Pulse** (ciągła aktualizacja prognoz liczbowych).
