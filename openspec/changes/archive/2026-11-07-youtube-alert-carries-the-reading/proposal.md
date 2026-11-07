## Why

Powiadomienie o filmie niesie dziś tylko krótkie streszczenie (`summary_pl`, do 900 znaków), a nie odczyt, który
model napisał promptem kanału. Operator ustawił prompt „Domyslny” tak, żeby odczyt miał sekcje („W skrócie”,
„Szczegółowe streszczenie”, tematy ze znacznikami czasu) — i na telefonie nie widzi z tego nic (26 października 2026,
film `3JA0foOeNDU`: odczyt 12 582 znaki, wiadomość ~700). Zmiana szablonu reguły tego nie naprawi: zdarzenie
`youtube.film.read` w ogóle nie niesie tekstu odczytu, a pakiet alertów i tak przycina treść do 3500 znaków, bo brama
odmawia wiadomości dłuższej niż limit Telegrama (4096).

## What Changes

- Gotowa treść zdarzenia „film odczytany” niesie **pełny tekst odczytu** zamiast streszczenia: ocena i kanał, tytuł,
  tekst odczytu, odnośnik. Treść ponad limit zdarzenia jest
  przycinana przez archiwum ze znakiem cięcia, a odnośnik zostaje.
- Limit treści zdarzenia (`EventIn.text`) i wypełnionego szablonu rośnie z 4000/3500 do 16 000 znaków.
- Pakiet alertów **wysyła długą treść w kolejnych wiadomościach**, każda w limicie jednej wiadomości bramy, dzieląc
  na granicy akapitu, potem linii, potem słowa. Odpalenie pamięta, ile części doręczono (`fires.parts_sent`), więc
  ponowienie po błędzie przejściowym wysyła tylko resztę. Sufit na godzinę liczy odpalenia, nie części.

Poza zakresem: formatowanie Markdown w Telegramie (tekst idzie jak dotąd, bez `parse_mode`), zmiana szablonu
istniejących reguł (domyślny `{text}` dostaje pełną treść sam).

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `youtube-data-alerts`: „Wiadomość prowadzi do filmu” — treść niesie tekst odczytu zamiast krótkiego streszczenia.
  Wymaganie w obecnym brzmieniu pochodzi z `youtube-prompts` (zmergowane, jeszcze niezarchiwizowane);
  **ta zmiana MUST zostać zarchiwizowana po niej**.
- `alerts-delivery`: nowe wymaganie — długa treść idzie w częściach, a ponowienie nie powtarza doręczonych.
  Zdolność powstaje w `alerts-package` (niezarchiwizowane); archiwizacja po niej.

Pominięte: `design.md` (jedna decyzja — dzielenie u pakietu alertów, nie w bramie, bo to pakiet alertów trzyma
ponowienia i musi wiedzieć, które części już doszły — jest tutaj) i `review.md` (mały zakres).

## Impact

- `modules/workbench/alerts`: `contract.py` (limit `EventIn.text`), `template.py` (limit i podział na części),
  `delivery.py` (wysyłka części), `store.py`, migracja `0004` (`fires.parts_sent`).
- `modules/workbench/youtube_data`: `alerts.py` (treść), `store.py` (`analysed_for_alert` czyta tekst odczytu), README.
- Kontrakty terminala: `contract:check` po zmianie limitu (`contract-sync`).
- Produkcja: po wdrożeniu workbencha; migracja stosuje się sama przy starcie.
