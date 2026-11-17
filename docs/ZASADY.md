# Zasady konkursu i jak bot ich pilnuje

| Zasada | Jak jest pilnowana |
|---|---|
| Każda prognoza ma komentarz z uzasadnieniem zgodnym z tym, co bot zrobił | Komentarz to pełne rozumowanie modelu i research (budowany przez bibliotekę). Bezpiecznik blokuje wysyłkę bez komentarza. Jeśli komentarz nie dojdzie, następne przejście dosyła go z rejestru. |
| Jeden właściciel = jeden bot kwalifikujący się do nagród | Po stronie właściciela: nie zakładaj drugiego konta bota. |
| Gotowość do pokazania kodu lub opisu działania | Kod jest w tym repozytorium, opis w README. |
| **Bez człowieka w pętli**: nie wolno podglądać prognoz bota na otwartych pytaniach i poprawiać go pod nie | Bot nie ma trybu „popraw tę prognozę”. Zmiany w promptach i ustawieniach testujemy tylko na `--mode test` (bot-testing-area) albo na pytaniach już zamkniętych. Logów z turnieju używamy tylko do sprawdzenia, czy usługa działa. |
| Jak w takim razie ulepszać bota | Polecenie `prognozy porownaj`: prognozy bez wysyłania na otwartych pytaniach **spoza turniejów botów** (pytania turniejowe są odfiltrowane), porównane z prognozą społeczności. |
| Ankieta po sezonie obowiązkowa | Po stronie właściciela (REJESTRACJA.md, punkt 6). |
| Dozwolony zakres prognoz | Binarne: 1–99%. Wielokrotny wybór: wszystkie opcje, suma 1. Liczbowe/daty: CDF ściśle rosnąca, właściwa liczba punktów i granice. Niespełnienie = brak wysyłki. |
| Brak zgadywania na ślepo | Gdy żadne źródło informacji nie odpowie, pytanie jest pomijane i wraca przy następnym przejściu. |
| Klucze i dane właściciela poza kodem | Klucze tylko w `/etc/prognozy/prognozy.env`; maskowane w logach; test pilnuje, że w repo nie ma plików `.env`. |

## Otwarty kod

Repozytorium nie zawiera kluczy ani danych właściciela, więc da się je upublicznić. Daje to mniej więcej podwójne kredyty i pewną kwalifikację do nagród (od jesieni 2026 boty komercyjne bez otwartego kodu nie dostają nagród). Przed upublicznieniem trzeba dodać licencję (np. MIT); decyzja należy do właściciela.
