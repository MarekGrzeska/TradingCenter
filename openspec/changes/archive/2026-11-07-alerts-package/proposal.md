## Why

Powiadomienie na Telegram ma dziś dwa zaszyte w kodzie powody (post z oceną ≥ progu z `.env`, film
według reguły kanału), a operator w terminalu tylko przekierowuje je, wpisując tekstem klucz celu.
Nie da się ustawić alertu „EURUSD powyżej 1,10” ani „zespół skończył przebieg”. „Czy” i „komu”
leżą w trzech miejscach. Research i pięć wariantów: `docs/telegram-wyzwalacze.html`; operator wybrał
C′ (osobny pakiet) razem z E (regułę opisuje się zdaniem).

## What Changes

- Nowy, dziewiąty pakiet workbencha **`alerts`** pod `/alerts`, z własną bazą `alerts`, łańcuchem
  migracji pod kluczem blokady `8120` i własnym zegarem. Montowany tylko przy ustawionej bazie.
- **Reguła powiadomienia** = źródło + filtr + adresat + szablon + czas martwy, jednorazowa albo
  powtarzalna. Zapisuje ją, zmienia i usuwa wyłącznie operator przez REST.
- **Źródło „stan”**: zegar odpytuje narzędzie tylko do odczytu, a reguła odpala na zboczu
  (przejście z „nie” w „tak”). Niedostępność narzędzia to trzeci stan, nie fałsz. Sprawdzanie
  nie kosztuje tokenów.
- **Źródło „zdarzenie”**: pakiety ogłaszają typy zdarzeń z JSON Schema atrybutów i publikują
  zdarzenia w procesie. Zdarzenia nie da się wstrzyknąć z zewnątrz. Filtr reguły działa na
  atrybutach.
- **Doręczenie**: `alerts` zapisuje odpalenie, wysyła przez `/telegram` po nazwie adresata, ponawia
  w oknie i pamięta wynik. Jedno zdarzenie daje co najwyżej jedno powiadomienie na regułę.
- **Szkic ze zdania (E)**: operator pisze zdanie, a model zwraca szkic reguły zbudowany z katalogu.
  Terminal pokazuje wypełniony formularz, który operator zatwierdza. Model nigdy nie zapisuje reguły
  i nigdy nie stoi w pętli sprawdzania. Brak klucza modelu to działająca konfiguracja.
- **Pierwsi producenci zdarzeń**: archiwum YouTube (film odczytany), archiwum postów (post
  odczytany), zespoły (przebieg zakończony).
- **BREAKING**: znikają cele i przypisania bramy Telegrama, reguła alertu kanału/tematu YouTube i
  próg postów `ALERT_MIN_IMPACT_SCORE`. Wszystko to przejmują reguły. Istniejące przypisania
  migrują do reguł automatycznie przy pierwszym starcie `alerts`.
- Nowa zakładka terminala **Alerty**: lista reguł ze stanem i historią, kreator, w którym każde pole
  wybiera się z listy, oraz pole na zdanie.

**Poza zakresem:** akcje inne niż Telegram (uruchomienie zespołu z reguły), godziny ciszy, zakładanie
reguł z pocketu i z rozmowy, zdarzenia z `trading-mcp` i z gateway'a. Każde z nich to osobna zmiana,
dla której ten pakiet jest już właściwym miejscem.

## Capabilities

### New Capabilities
- `alerts-rules`: kształt reguły, walidacja przy zapisie względem katalogu, kto zmienia,
  jednorazowość, wyłączanie.
- `alerts-conditions`: źródło „stan”: narzędzie tylko do odczytu, zbocze, czas martwy, trzeci stan,
  zero tokenów, najkrótszy interwał.
- `alerts-events`: typy zdarzeń ze schematem, publikacja tylko w procesie, idempotencja, filtr,
  retencja.
- `alerts-delivery`: odpalenie, doręczenie przez bramę, ponowienie w oknie, deduplikacja, sufit
  wysyłek reguły.
- `alerts-drafts`: szkic reguły ze zdania (E).
- `alerts-api`: kontrakt REST, trasa stanu, dostęp wołających, narzędzia dla rozmowy.
- `terminal-alerts`: zakładka Alerty.

### Modified Capabilities
- `workbench-process`: pakiet alertów jest obecny z konfiguracji albo nieobecny.
- `telegram-gateway-purposes`: usunięta w całości (cele i przypisania).
- `telegram-gateway-delivery`: wiadomość adresowana wyłącznie nazwą adresata.
- `telegram-gateway-bots`, `telegram-gateway-destinations`: znika odmowa usunięcia „z przypisaniem”.
- `terminal-telegram`: zakładka bez celów i przypisań.
- `social-data-alerts`: post odczytany staje się zdarzeniem, a próg przechodzi do reguł.
- `youtube-data-alerts`, `youtube-data-tools`, `terminal-youtube`: film odczytany staje się
  zdarzeniem, a reguła kanału znika.
- `teams-runs`: zakończony przebieg jest publikowany jako zdarzenie.

**Kolejność archiwizacji:** ta zmiana modyfikuje wymagania, które wnoszą
`telegram-bots-from-the-terminal` i `add-youtube-archive`. Archiwizuje się ją po nich.

## Impact

- `modules/workbench`: nowy pakiet `alerts/`, `alembic-alerts.ini`, montaż i przekazanie klientów
  w `workbench/app.py`, wpis w `tests/test_layering.py` i w `scripts/tests/test_pool_budget.py`,
  blok `ALERTS_*` w `.env.example`. W `telegram_gateway`, `youtube_data`, `social_data` i `teams`
  wysyłka zastąpiona publikacją zdarzenia. Migracje usuwają `purposes`, `assignments` i
  `alert_rule`.
- `modules/terminal`: `src/alerts/`, wygenerowany `contract.alerts.generated.ts`, przebudowana
  zakładka Telegram, regenerowane kontrakty `telegram` i `youtube` (skill `contract-sync`).
- `scripts/dev.py`, `deploy/postgres/ensure-databases.sh`, `deploy/env.required`: baza i rola
  `alerts`, `ALERTS_DATABASE_URL`, opcjonalnie `ALERTS_OPENAI_API_KEY`.
- `review.md` zostanie napisany po zadaniach. Zmiana dodaje drogę wejścia zdarzeń, wywołanie modelu
  i zapis kasujący dane dwóch pakietów, więc na review zasługuje.
