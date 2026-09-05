## 0. Decyzja i pomiar, bez kodu

- [ ] 0.1 Operator potwierdza odwrócenie reguły (proposal.md, „What Changes", pierwszy punkt) — bez tego etapy 2–5 nie ruszają
- [x] 0.2 Pomiar sidecara Auth (283 → 178 MB, sidecar ≈ 105 MB; design.md): godzina bez `auth_settings_v2` na `app-tradingcenter-telegram-gateway`, odczyt `AverageMemoryWorkingSet` przed i po, powrót; liczba do design.md („Sidecar Auth mierzy się przed etapem 2")
- [ ] 0.3 Jeśli Auth ≥ 100 MB: ten plan czeka, powstaje osobna propozycja „walidacja JWT w module"; jeśli < 100 MB: dalej

## 1. Szkielet gospodarza (bez zmian w infrastrukturze)

- [x] 1.1 `tests/test_layering.py` w workbenchu: mapa zakazów generowana z listy pakietów (`PACKAGES`), składanie nazwane osobno; siódmy pakiet to jedna pozycja na liście, nie edycja testu
- [x] 1.2 `workbench/assembly.py`: `mount_package(app, prefix, subapp, state)` — montaż pod-aplikacji pod przedrostkiem z zapełnieniem `subapp.state` przez gospodarza; jeden test, że trasy pod-aplikacji odpowiadają pod przedrostkiem i że `/health` gospodarza nie koliduje z `/health` pakietu
- [x] 1.3 Obraz workbencha lokalnie w Dockerze: RSS pod ruchem, liczba do tabeli w design.md zamiast „≈" — 173 MB, wpisane
- [x] 1.4 `polymarket-data`: szczyt 655 MB — hipoteza o `/events/{id}/changes` obalona (odczyty `LIMIT 1` po indeksie); przyczyną był backfill wszystkich outcome'ów naraz; ograniczony do czterech równocześnie, jeden test (PR #245)
- [x] 1.5 `market-data`: obliczenia wskaźników w `asyncio.to_thread`, jeden test, że pętla nie stoi w czasie obliczenia (318 ms → < 150 ms) (PR #244)

## 2. Trzy pętle tego samego kształtu — jeden PR na moduł, w tej kolejności

- [x] 2.1 **polymarket-data → `workbench/polymarket_data/`**: pakiet przeniesiony bez zmiany nazw; montaż pod `/polymarket`; `POLYMARKET_DATABASE_URL` i reszta z przedrostkiem tam, gdzie istnieje podwójnie; migracja pod kluczem 8070 i pętla próbkowania w lifespan gospodarza; heartbeat w `/health` gospodarza; źródło narzędzi w procesie w obu rejestrach (te same nazwy, opisy, sufity, odmowy); `POLYMARKET_MCP_URL`/`_SCOPE` znikają z workbencha; `dev.py` mówi o starym pliku `.env`
- [x] 2.2 Terraform dla 2.1 (napisane; apply operatora przed merge): `azurerm_linux_web_app.polymarket_data` znika z regułą firewalla, tożsamością, rejestracjami `polymarket_data_terminal`/`_pocket` i dotacją Key Vault; alert `polymarket-data-loop-stopped` wskazuje workbench; **plan czyta `0 to add` na dotacji workbencha**; operator: `grant-schema-ownership.sql` dla `app-tradingcenter-agent` na `polymarket` przed apply
- [x] 2.3 Terminal i pocket dla 2.1: `VITE_POLYMARKET_HTTP` → adres workbencha + `/polymarket`, scope polymarket → scope workbencha; `contract:generate`, `contract:check` zielone
- [x] 2.4 CI/deploy dla 2.1: job `polymarket-data` i `deploy-polymarket-data.yml` znikają; `changes` w `checks.yml` widzi nowy pakiet jako workbench
- [x] 2.5 Bramka 2.1: doba z zielonym alertem pętli na nowej metryce; working set workbencha zmierzony i wpisany do tabeli design.md — skrócona decyzją operatora 5 września (metryki pętli obu archiwów wróciły po #248, alerty z danymi; working set workbencha z dwoma archiwami ≈ 340 MB, w design.md)
- [x] 2.6 **social-data → `workbench/social_data/`**: to samo co 2.1–2.4, przedrostek `/social`, klucz 8090; `TELEGRAM_GATEWAY_*` social-data staje się ustawieniem workbencha; lista wołających telegram-gateway dostaje tożsamość workbencha zamiast social-data (PR nadbudowany na #246; bramka jak 2.5 — doba obserwacji po apply i merge — osobno)
- [x] 2.7 **strategy → `workbench/strategy/`**: to samo, przedrostek `/strategy`, klucz 8080; `MARKET_DATA_URL/_SCOPE` zostają jako ustawienia workbencha (3a: HTTP po publicznym hostname); listy wołających market-data i telegram-gateway dostają tożsamość workbencha; `STRATEGY_MCP_URL` znika (zegar teams szuka `pending_setups` po nazwie w każdym źródle, także lokalnym)
- [x] 2.8 Bramka etapu 2: pięć aplikacji, alerty trzech pętli zielone przez dobę, suma working setów w tabeli; docs: CLAUDE.md tabela modułów i porty (8070, 8080, 8090 stają się niczyje), `docs/architecture.md` diagram — pięć aplikacji od 5 września ~11:35 UTC, metryki trzech pętli z danymi, working set 357–375 MB w design.md; doba obserwacji skrócona decyzją operatora

## 3. market-data do gospodarza, i godzina na B2

- [ ] 3.1 Decyzja o nazwie katalogu gospodarza (design.md, Open Questions) — przed tym PR-em, bo od niego market-data przestaje być słowem w tabeli
- [ ] 3.2 **market-data → pakiet gospodarza**: montaż pod `/market`, `/ws/candles` → `/market/ws/candles` z tym samym biletem; migracja pod kluczem 8020, ingest, rollupy, jobs, gauge wieku świec w lifespan gospodarza; `MARKET_DATABASE_URL` i przedrostki; źródło jedenastu narzędzi w procesie, `MARKET_MCP_URL`/`_SCOPE` znikają
- [ ] 3.3 strategy przechodzi na wstrzyknięty protokół `Archive` (3b): `archive.py` i `_ManagedIdentityAuth` znikają, `MARKET_DATA_URL/_SCOPE` znikają; jeden test integracji, że strategia widzi te same świece co REST
- [ ] 3.4 Brama: `MODULE_CALLER_APPLICATION_IDS` i `allowed_applications` dostają tożsamość gospodarza zamiast market-data; `GATEWAY_*` stają się ustawieniami gospodarza
- [ ] 3.5 Terraform: `azurerm_linux_web_app.market_data` znika jak w 2.2; alerty `candle_age`, `database_unreachable` (scope bazy bez zmian) i web test `/ping` → `/market/ping` wskazują gospodarza; rejestracje `terminal`/`pocket` dla market-data znikają; plan `0 to add` na dotacji
- [ ] 3.6 Terminal i pocket: `VITE_ARCHIVE_HTTP`/`_WS` → gospodarz + `/market`, jeden scope; kontrakty zielone
- [ ] 3.7 Bramka 3: cztery aplikacje, `candle_age` zielony przez dobę z otwartym rynkiem, working set w tabeli
- [ ] 3.8 **Godzina na B2**: spokojna godzina z otwartym rynkiem, `az appservice plan update --sku B2`, `MemoryPercentage` co 5 minut, które aplikacje restartowały, powrót tą samą komendą z `B3`; wynik do design.md jako liczba zamiast dwóch kolumn
- [ ] 3.9 Decyzja z 3.8: < 85% → etap 5; 85–100% → etap 4; restarty/OOM → B3 zostaje, etap 5 bez SKU, powód przy `sku_name` w `app-service.tf`

## 4. Warunkowo: telegram-gateway do gospodarza

- [ ] 4.1 Tylko po 3.9 „85–100%": pakiet pod `/telegram`, klucz 8100, boty i pula bez zmian; `TELEGRAM_MCP_URL` znika; `TELEGRAM_GATEWAY_*` z 2.6/2.7 stają się wywołaniem w procesie przez wstrzyknięty protokół `Notifier`
- [ ] 4.2 Terraform i CI jak w 2.2/2.4; `telegram_gateway_cli` (rejestracja CLI) zostaje, bo to nie tożsamość aplikacji
- [ ] 4.3 Druga godzina na B2, ten sam protokół co 3.8; decyzja jak w 3.9 bez dalszego etapu 4

## 5. Zamknięcie

- [ ] 5.1 Zmiana OpenSpec dla `infra/`: `sku_name = "B2"` z pomiarem obok, jeśli 3.9/4.3 tak powiedziały; w przeciwnym razie komentarz przy `"B3"` z liczbą
- [ ] 5.2 `DROP ROLE` dla tożsamości zwiniętych modułów, po tygodniu bez błędu połączenia w logach
- [ ] 5.3 Obrazy zwiniętych modułów w GHCR mogą zniknąć; `deploy_gate.py` i mapa `dev.py` bez martwych wpisów
- [ ] 5.4 Dokumenty: CLAUDE.md (reguła nośna, tabela, porty, „Things that will bite you"), `docs/architecture.md`, `docs/mniej-modulow-czy-aks.html` do `docs/archive/` z notą o zmienionej liczbie, pięć przewodników → jeden
- [ ] 5.5 `review.md` według szablonu: liczby z każdej bramki, co odbiegło od design.md, na którym etapie plan stanął, jeśli stanął
