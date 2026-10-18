## 1. Brama Telegrama: adresat i wiązanie

- [x] 1.1 Migracja `telegram`: tabela `recipients`, `destinations.recipient_id` (uzupełnienie po nazwie, `NOT NULL`, klucz obcy `ON DELETE CASCADE`, `UNIQUE (recipient_id, bot_id)`), zdjęcie unikalności `name` przy zachowaniu kolumny; test migracji na bazie z istniejącymi wiązaniami
- [x] 1.2 `store` i `models`: adresat (zakładanie, lista z wiązaniami, usunięcie), wiązanie po (adresat, bot), `binding` wiąże po `recipient_id`; `destination_by_name` zastąpione
- [x] 1.3 Trasy: `GET/POST /recipients`, `DELETE /recipients/{name}`, `POST /recipients/{name}/bots`, `DELETE /recipients/{name}/bots/{bot}`; `/destinations` usunięte; `caller_access` i `openapi`
- [x] 1.4 `POST /messages` z `{recipient, bot?}`: bez bota przy jednym wiązaniu, `409` z listą botów przy kilku, odmowa dla bota spoza adresata i dla adresata bez wiązania
- [x] 1.5 Blokada i stan per wiązanie (test: zablokowany jeden bot nie rusza drugiego); narzędzia MCP bramy i ich opisy

## 2. Pakiet alertów: reguła z botem

- [x] 2.1 Migracja `alerts`: `rules.bot text NULL`
- [x] 2.2 `contract`, `store`, `rules`: pole `bot` w regule i w odpowiedziach
- [x] 2.3 `gateway.send(destination, bot, text)`; `delivery` przekazuje bota; odmowa dwuznaczności jest ostateczna z powodem nazywającym boty
- [x] 2.4 `validation`: bot spoza adresata i brak bota przy kilku wiązaniach to wady przy polu `bot`, razem z pozostałymi; `known` niesie wiązania
- [x] 2.5 Wada stanu reguły: `rules_with_defects` liczy dwuznaczny adres i bota, którego adresat już nie ma
- [x] 2.6 Szkic ze zdania: bot zostaje pusty, a ten sam walidator wskazuje wybór przy adresacie o kilku botach (model nie wybiera bota)

## 3. Terminal

- [ ] 3.1 Zakładka Telegram: adresaci z wiązaniami i ich stanem, „dodaj przez kolejnego bota” z odnośnikiem startowym i komunikatem o tapnięciu; ostrzeżenie o regułach bez bota
- [ ] 3.2 Usunięcie wiązania z nazwą bota w potwierdzeniu; usunięcie adresata wymienia jego boty
- [ ] 3.3 Formularz reguły: „Którym botem” z botami wybranego adresata; lista reguł mówi, przez którego bota; edycja starej reguły wypełnia jedynego bota
- [ ] 3.4 Regeneracja kontraktów `telegram` i `alerts` (`contract-sync`), testy widoków wg „How much test is enough”

## 4. Dokumentacja i wdrożenie

- [ ] 4.1 README bramy i pakietu `alerts`, `docs/architecture.md` jeśli opisuje adresata
- [ ] 4.2 Osobna, późniejsza zmiana: usunięcie kolumny `destinations.name` po jednym zweryfikowanym wydaniu
- [ ] 4.3 Po scaleniu `deploy-watch`; dopiero po wdrożeniu dodanie drugiego bota przez operatora (Migration Plan, pkt 3)
