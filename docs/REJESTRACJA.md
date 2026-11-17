# Rejestracja: co robi właściciel

Bot sam niczego nie zakłada. Poniższe kroki wykonujesz Ty, raz (punkt 4 co sezon).
Linki i nazwy przycisków na stronie Metaculus mogą się zmieniać. Aktualny opis jest na stronie zasobów: https://www.metaculus.com/notebooks/38928/ai-benchmark-resources/

## 1. Konto bota na Metaculus

1. Zaloguj się na swoje zwykłe konto Metaculus (albo je załóż).
2. Wejdź na https://www.metaculus.com/futureeval/participate/ i utwórz konto bota.
   - Nazwa bota będzie widoczna w rankingu. Nie musi zawierać Twojego nazwiska.
3. Skopiuj **token bota**. To jest `METACULUS_TOKEN`.
   - Token daje pełny dostęp do konta bota. Nie wysyłaj go mailem ani na czacie; wpisz go tylko na serwerze (patrz WDROZENIE.md).

Pamiętaj: **jeden właściciel = jeden bot kwalifikujący się do nagród.**

## 2. Formularz uczestnika (obowiązkowy)

1. Otwórz formularz: https://forms.gle/aQdYMq9Pisrf1v7d8
2. Wypełnij pierwszą część (3 wymagane pytania). Bez tego prognozy bota się nie liczą.
3. W tym samym formularzu jest **wniosek o kredyty AI**. Zaznacz, że chcesz kredyty.
   - Jeśli planujesz otwarty kod, napisz to. Boty z otwartym kodem dostają mniej więcej podwójne kredyty.
   - Kredyty są przyznawane wybiórczo. Może się zdarzyć, że ich nie dostaniemy; wtedy potrzebny jest własny klucz OpenRouter z małym budżetem.

## 3. Klucz OpenRouter

- Kredyty od Metaculus przychodzą jako klucz OpenRouter. To jest `OPENROUTER_API_KEY`.
- Jeśli kredytów jeszcze nie ma: załóż konto na https://openrouter.ai, ustaw **limit wydatków** (np. 20 $) i utwórz klucz.

## 4. AskNews (drugie źródło wiadomości, co sezon)

1. Załóż konto na https://my.asknews.app/ **na ten sam e-mail co konto bota na Metaculus**.
2. Poproś o aktywację darmowego dostępu: mail na contact@asknews.app (albo wiadomość do @freqai na Discordzie AskNews) z nazwą bota, e-mailem konta AskNews, imieniem i nazwiskiem, profilem LinkedIn i informacją „independent”.
3. Poczekaj na potwierdzenie, że darmowe wywołania są aktywne.
4. Wygeneruj klucz na https://my.asknews.app/en/settings/api-credentials. To jest `ASKNEWS_API_KEY`.

Limity: 1000 wywołań miesięcznie, 4000 na cały turniej. Jedno konto na osobę, tylko do tego konkursu, odnawiane co sezon.
Bez AskNews bot też działa (wyszukiwanie przez OpenRouter + rynki), tylko z mniejszą liczbą źródeł.

## 5. Discord (opcjonalnie, ale warto)

Kanał „build a forecasting bot” na Discordzie Metaculus: tam ogłaszane są zmiany ID turniejów, API i kredytów.
https://discord.com/invite/NJgCC2nDfh

## 6. Po sezonie (obowiązkowe)

- **Ankieta po sezonie.** Bez niej nie ma nagrody.
- Przy wypłacie Metaculus może poprosić o formularz podatkowy i dane do przelewu.
- Nagroda to dochód: ustal z księgowym, jak ją wykazać przy ZZP w Holandii.

## Lista kontrolna

- [ ] Konto bota założone, token zapisany na serwerze
- [ ] Formularz uczestnika wypełniony (3 pytania + wniosek o kredyty)
- [ ] Klucz OpenRouter (z kredytów albo własny z limitem)
- [ ] AskNews: ASKNEWS_API_KEY
- [ ] `prognozy check` na serwerze pokazuje OK
- [ ] Próba na pytaniach testowych przeszła (WDROZENIE.md, krok 4)
- [ ] Włączone wysyłanie i timer
