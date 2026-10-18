## 1. Szkielet pakietu

- [x] 1.1 `alerts/` z `config.py` (prefiks `ALERTS_`: baza, pula 2, tick, najkrótszy interwał, okno ponowień, sufit/h, retencja, klucz i model szkicu, sufit dobowy szkiców), `runtime.py` (klucz blokady `8120`), `app.py`, `openapi.py`
- [x] 1.2 `alembic-alerts.ini` i migracja: `event_types`, `events` (unikalne `(type, source_key)`), `rules`, `rule_checks`, `fires` (unikalne `(rule_id, event_id)` i `(rule_id, edge_at)`), `draft_usage`, `migrations_done`; indeksy częściowe z design 7
- [x] 1.3 `caller_access.py`: trasy operatora z listy aplikacji, trasy producentów wyłącznie dla `IN_PROCESS_CALLER`
- [x] 1.4 Montaż warunkowy w `workbench/app.py`, kolejność lifespanów z design 8, wpis w `tests/test_layering.py` i `scripts/tests/test_pool_budget.py`
- [x] 1.5 `scripts/dev.py` (`LOGICAL_DATABASES`, łańcuch), `.env.example`, `deploy/postgres/ensure-databases.sh`, `deploy/env.required` (`ALERTS_DATABASE_URL`)
- [x] 1.6 Testy: start bez bazy, baza nieosiągalna (odmowa z nazwą), migracja pod blokadą (`-m db`)

## 2. Katalog i reguły

- [ ] 2.1 Katalog narzędzi: podzbiór `local_tools` z `READ_ONLY` przekazany przez assembly, pola liczbowe wyliczane z `outputSchema`
- [ ] 2.2 `PUT /alerts/event-types/{name}` (tylko w procesie) i oznaczanie reguł, którym nowy schemat zabrał pole
- [ ] 2.3 Model `RuleIn` i walidacja zapisu wobec katalogu i listy adresatów bramy (`alerts-rules`)
- [ ] 2.4 REST reguł: lista ze stanem i wadami, tworzenie, zmiana, włącz/wyłącz, usunięcie
- [ ] 2.5 Podstawiacz szablonu `{name}` (bez `str.format`), cięcie do limitu bramy, podgląd
- [ ] 2.6 Testy jednostkowe walidacji (każdy powód odrzucenia raz) i szablonu; jeden test REST na trasę

## 3. Źródło „stan”

- [ ] 3.1 `conditions.py`: kopia chodzenia po polu, porównania, zbocza i czasu martwego z `teams/scheduler/clock.py`, z trzecim stanem porównywanym z ostatnim znanym wynikiem
- [ ] 3.2 Zegar: zajęcie należnych reguł (`SKIP LOCKED`), wywołanie narzędzia, zapis `rule_checks`, odpalenie przy zboczu
- [ ] 3.3 Kreator proponuje high/low tworzącej się świecy dla porównań ceny; tryb jednorazowy wyłącza regułę po doręczeniu
- [ ] 3.4 Testy: zbocze raz, miganie w czasie martwym, niedostępność ≠ fałsz, powrót po niedostępności bez fałszywego zbocza, zero wywołań modelu
- [ ] 3.5 `db-cost-check` dla zajęcia reguł i odczytu `get_last_price` przy 20 regułach co 30 s

## 4. Źródło „zdarzenie”

- [ ] 4.1 `POST /alerts/events`: walidacja wobec schematu, idempotencja, odpalenia pasujących reguł w tej samej transakcji, pobudka zegara
- [ ] 4.2 Filtr: równość, lista, porównania liczbowe, zawieranie; testy jednostkowe dopasowania
- [ ] 4.3 Retencja zdarzeń raz na godzinę; odpalenia zostają
- [ ] 4.4 Test, że żądanie z krawędzi (token terminala, klucz wspólny) jest odmową i nic nie zapisuje

## 5. Doręczenie

- [ ] 5.1 Klient bramy w procesie, wysyłka po nazwie adresata, klasyfikacja odmowy trwała/przejściowa
- [ ] 5.2 Ponowienie z `retry_after`, odpuszczenie po oknie, brak bramy jako stan
- [ ] 5.3 Sufit wysyłek reguły na godzinę i jedna wiadomość o zdławieniu
- [ ] 5.4 Testy: restart między zapisem a odpowiedzią bramy nie daje drugiego odpalenia (`-m db`), zalew zdławiony do sufitu

## 6. Szkic ze zdania

- [ ] 6.1 `POST /alerts/drafts`: katalog przycięty do promptu, jedno wywołanie ze schematem `RuleIn` + `defects`, walidacja zapisu na wyniku
- [ ] 6.2 Zapis zużycia, dobowy sufit, brak klucza jako odmowa nazywająca ustawienie
- [ ] 6.3 Testy na zapisanych odpowiedziach modelu: szkic poprawny, szkic z nieśledzonym instrumentem, domyślny adresat nazwany

## 7. Trasa stanu i narzędzia

- [ ] 7.1 `GET /alerts/state` (`alerts-api`)
- [ ] 7.2 Narzędzia `alert_rules` i `alert_fires` podpięte w `workbench/local_tools.py`; test, że brak narzędzia zapisującego

## 8. Producenci

- [ ] 8.1 Klient `alerts` w procesie przekazywany przez assembly do `youtube_data`, `social_data` i `teams` (brak pakietu = `None`)
- [ ] 8.2 YouTube: ogłoszenie `youtube.film.read`, publikacja każdego odczytanego filmu, znacznik po przyjęciu; usunięcie `_wanted`
- [ ] 8.3 Social: ogłoszenie `social.post.read`, publikacja każdego ocenionego posta, znacznik po przyjęciu; koniec czytania `ALERT_MIN_IMPACT_SCORE`
- [ ] 8.4 Teams: ogłoszenie `teams.run.finished`, publikacja po stanie końcowym z ponowieniem
- [ ] 8.5 Trasy stanu producentów mówią „nie publikuje”, gdy `alerts` nie ma

## 9. Migracja danych (wdrożenie 1)

- [ ] 9.1 Jednorazowa migracja w lifespanie `alerts`: przypisania → reguły, reguły kanałów/tematów → reguły z filtrem, próg postów → filtr; znacznik w `migrations_done`
- [ ] 9.2 Trasy celów i przypisań bramy odpowiadają `410`; `POST /telegram/messages` z celem jest odmową
- [ ] 9.3 Test migracji na danych z `*`, przedrostka, kanału „zawsze”, „od progu” i „nigdy” (`-m db`)

## 10. Terminal

- [ ] 10.1 `contract.alerts.generated.ts` i regeneracja kontraktów `telegram`, `youtube` (skill `contract-sync`)
- [ ] 10.2 Zakładka Alerty: lista reguł ze stanem i wadami, historia odpaleń
- [ ] 10.3 Kreator z wyborami z katalogu, pola filtra ze schematu, podgląd szablonu, odmowa przy polu
- [ ] 10.4 Pole na zdanie: szkic otwiera kreator z wadami przy polach; stan „szkice niedostępne”
- [ ] 10.5 Zakładka Telegram bez celów i przypisań, ostrzeżenie przy usuwaniu bota/adresata; zakładka YouTube bez reguły alertu, odesłanie do Alertów
- [ ] 10.6 Testy wg reguły CRUD (szczęśliwa ścieżka, błąd, odmowa) dla reguł; jeden test szkicu

## 11. Wdrożenie 2 i dokumentacja

- [ ] 11.1 Migracje usuwające `purposes`, `assignments` (telegram) i `alert_rule` (youtube); usunięcie kodu celów i przypisań
- [ ] 11.2 `ALERT_MIN_IMPACT_SCORE` w `RETIRED_SETTINGS`
- [ ] 11.3 `alerts/README.md`; aktualizacja README `telegram_gateway`, `modules/workbench/README.md`, tabeli w `CLAUDE.md` (dziewięć pakietów) i `docs/architecture.md`
- [ ] 11.4 Po każdym wdrożeniu skill `deploy-watch`
