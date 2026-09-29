## 1. Przechowywanie

- [x] 1.1 Migracja łańcucha `social`: tabele `news_items` (z `kept_at`) i `news_sources` z kluczem i indeksami z design.md (decyzje 1 i 5)
- [x] 1.2 `store.py` (albo `news_store.py`): zbiorowy insert newsów `ON CONFLICT DO NOTHING` z `first_seen_at` i `previous_fetch_at`; zapis udanego pobrania i porażki źródła; odczyt okna z zawężeniami, porządkiem i `truncated`; rachunek opóźnień per źródło (`percentile_cont`, tolerancja 120 s); postawienie i zdjęcie `kept_at`; czyszczenie po retencji z pominięciem zachowanych
- [x] 1.3 Testy `-m db`: news widziany drugi raz niczego nie zmienia; zastany ma pustą `previous_fetch_at`; granice 3/5 min i 0/1 min ze scenariuszy; czas z przyszłości i brak czasu wypadają ze statystyk; źródło bez pomiarów ma statystyki puste; czyszczenie usuwa stary niezachowany, zostawia zachowany, usuwa stary po zdjęciu znacznika
- [x] 1.4 `db-cost-check` dla odczytu okna i rachunku źródeł; EXPLAIN na 100 tys. wierszy (sufit retencji): wszystkie zapytania po indeksach, okno 6 h 19 buforów / 0,26 ms, rachunek źródeł 153 bufory / 1 ms, czyszczenie 3 bufory — klasa C2

## 2. Pobieranie

- [x] 2.1 `news_sources.py`: rekord źródła i lista startowa z design.md (15 wpisów)
- [x] 2.2 Parser RSS 2.0/Atom na `defusedxml`: guid albo link, daty RFC 822/ISO 8601, `<source>` Google News jako wydawca, czysty tekst z rozwiniętymi encjami, lead ≤ 1 000 znaków; testy jednostkowe na próbkach feedów zapisanych w `tests/social/fixtures/`
- [x] 2.3 Pobranie jednego źródła: warunkowy GET z `ETag`/`Last-Modified` w pamięci, 304 jako sukces, rozróżnione odmowa / brak odpowiedzi / nieczytelny dokument; własny User-Agent bez żadnego udawania
- [x] 2.4 Pętla `news`: takt `SOCIAL_NEWS_TICK_SECONDS` (30), źródła z minionym odstępem, semafor 4, timeout 20 s, porażka źródła nie przerywa przebiegu; czyszczenie raz na godzinę (`SOCIAL_NEWS_RETENTION_DAYS`, 28); heartbeat `news` bije po przebiegu
- [x] 2.5 Testy pętli na atrapie HTTP: jedno źródło pada, reszta zapisana; 304 przesuwa `last_success_at`; źródło nie jest pytane przed upływem odstępu; przebieg z wyjątkiem nie bije heartbeatu
- [x] 2.6 `app.py` `serving`: druga heartbeat w `Heartbeats`, start i stop pętli newsów obok zbioru postów; ustawienia `SOCIAL_NEWS_*` w `config.py`, `workbench/config.py` i `.env.example`

## 3. Kontrakt

- [x] 3.1 `contract.py`: `NewsItemOut` (z `kept_at`, `expires_at`), `NewsOut` (z `truncated`), `NewsSourceOut`, `NewsSourcesOut`, `KeepIn`; pola zawsze obecne, braki jako `null`, powód braku opóźnienia jako enum
- [x] 3.2 `routers/news.py`: `GET /news` (godziny albo od–do, `source` wielokrotny, `q`, `limit`) z odmową okna odwróconego; `GET /news/sources` z każdym zadeklarowanym źródłem; `GET /news?kept=true`; `PUT /news/keep` (para w ciele, nie w ścieżce) idempotentny, 404 dla nieznanej pary
- [x] 3.3 Wpisy `/news`, `/news/sources` i `/news/keep` w `RECORD` w `caller_access.py`, na powierzchni REST
- [x] 3.4 Po jednym teście, że stan dociera na drut dla każdej trasy, plus odmowa okna odwróconego, 404 znacznika i test, że znacznik nie zmienia treści newsa
- [x] 3.5 `contract-sync`: regeneracja `contract.social.generated.ts` w terminalu i w pocket

## 4. Terminal

- [x] 4.1 `src/news/newsApi.ts`: mapowanie z drutu na domenę (daty, granice, powód), przez `socialIdentity` i `Endpoints.socialHttp`; test mappera
- [x] 4.2 `NewsView`: okno (1/6/24 h, domyślnie 6), zawężenie po źródłach i tekście, liczba i obcięcie, karta z zakresem opóźnienia albo powodem, przycisk zachowania z powrotem po odmowie i momentem zniknięcia, widok „zachowane”, odświeżanie co 30 s bez gubienia listy przy błędzie
- [x] 4.3 Zestawienie źródeł: stan, ostatnie udane pobranie, mediana i p90 obu granic, wiek najnowszego, liczba; wyróżnienie stojących i odmawiających z powodem; pusta lista odróżnia „brak newsów” od „zbiór stoi”
- [x] 4.4 Wpis `news` w `src/app/tabs.ts`
- [x] 4.5 Testy widoku: happy path, jeden błąd odświeżenia, jedno źródło odmawiające, zachowanie z odmową kontraktu; formatowanie zakresu opóźnienia jako test jednostkowy funkcji

## 5. Pocket

- [x] 5.1 `src/news/`: `api.ts`, `useNews.ts` (60 s, ukryty ekran nie odpytuje), `NewsScreen` z listą i arkuszem źródeł, karta z opóźnieniem i przyciskiem zachowania
- [x] 5.2 Czwarta zakładka: `tabs.ts`, `LABELS` i ikona w `TabBar.tsx`, panel w `App.tsx`
- [x] 5.3 Testy: happy path, błąd odświeżenia, zachowanie z odmową, mapper

## 6. Dokumentacja i zamknięcie

- [x] 6.1 `social_data/README.md`: pętla newsów, lista źródeł, jak dołożyć feed, znaczenie granic opóźnienia; `docs/zrodla-newsow.html` wskazuje tę zmianę jako wykonaną
- [x] 6.2 Workbench: `uv run pytest` (z `-m db`), `ruff check .`, `pyright`; terminal i pocket: `pnpm test`, `lint`, `typecheck`, `contract:check`
- [x] 6.3 `openspec validate news-arrives-with-its-delay --strict`
- [ ] 6.4 Po wdrożeniu: `/social/news/sources` wymienia 15 źródeł z udanym pobraniem, `/social/health` niesie heartbeat `news`; odmawiające źródła zapisane w `review.md`
- [x] 6.5 `review.md`

## 7. Po pierwszym dniu na produkcji

- [x] 7.1 Times of Israel: własny feed odpowiada 403 z Azure (Cloudflare), więc wpis zastąpiony zapytaniem Google News `site:timesofisrael.com`
- [x] 7.2 Treść newsa: migracja `0004` (`content`), parser bierze `content:encoded`/Atom `content` z akapitami, kontrakt niesie `content`, testy parsera, magazynu i drutu
- [x] 7.3 Okna w minutach: `GET /news?minutes=`, test okna 5 i 15 minut
- [x] 7.4 Terminal: kliknięcie rozwija cały news w miejscu, okna 5 min–7 d (domyślnie 4 h), sortowanie po publikacji / zobaczeniu / oczekiwaniu, „Wszystkie / Żadne / Tylko działające”
- [ ] 7.5 Pocket: to samo co 7.4
- [ ] 7.6 Uzupełnić `review.md` o tę zmianę i po wdrożeniu sprawdzić, które feedy niosą treść
