## 1. Szkielet modułu

- [x] 1.1 Założyć `modules/social-data` z `pyproject.toml` (uv, ruff, pyright, pytest), biorąc `tc-runtime` i `tc-mcp-kit`
- [x] 1.2 `config.py` — odstęp zbioru, okno, dostęp do modelu i jego dwa modele, adres bazy, zapis dostępu; odmowa startu przy zdalnym hoście bez użytkownika
- [x] 1.3 `runtime.py` — położenie migracji i klucz blokady 8090
- [x] 1.4 `app.py` — `lifespan` migrujący bazę pod blokadą przed serwowaniem, `/health` niosące nazwę modułu
- [x] 1.5 `Dockerfile` i `README.md` modułu

## 2. Przechowywanie

- [x] 2.1 Migracja `0001` — tabela postów z kluczem `(source, external_id)`, indeksami po czasie publikacji i po ocenie, oraz tabela zużycia modelu
- [x] 2.2 `store.py` — wstawienie pomijające duplikaty, odczyt oknem z zawężeniami, odczyt jednego posta, zapis odczytu modelu i zużycia
- [x] 2.3 Testy `-m db` na dedupie, oknie i porządku wyniku

## 3. Zbiór

- [x] 3.1 `providers/__init__.py` — protokół źródła i rejestr
- [x] 3.2 `providers/truth_social.py` — pobranie feedu po dacie, parser dokumentu, czysta treść z rozwiniętymi encjami, rozpoznanie podania dalej
- [x] 3.3 Testy parsera na zapisanym dokumencie: encje, znaczniki, podanie dalej, wpis bez identyfikatora, dokument nieparsowalny
- [x] 3.4 `ingest.py` — pętla w `lifespan`, okno przez każdą dotkniętą datę UTC, filtr do okna, moment ostatniego udanego zbioru
- [x] 3.5 Zapis momentu początku zbioru przy pierwszym uruchomieniu; brak dociągania przeszłości
- [x] 3.6 Testy: okno przez północ, cichy feed nie rusza archiwum ani momentu zbioru, pusty dzień go aktualizuje

## 4. Wzbogacenie

- [x] 4.1 `enrichment.py` — jedno wywołanie modelu ze sztywnym schematem odpowiedzi, osobno tłumaczenie
- [x] 4.2 Zapis odczytu ze stemplem modelu i czasu, nadpisywanie poprzedniego, zapis zużycia obok
- [x] 4.3 Odrzucenie odpowiedzi spoza zakresu 1–10 i nieodczytywalnej — post zostaje niewzbogacony
- [x] 4.4 Wpięcie w pętlę zbioru: błąd jednego posta nie przerywa serii ani zbioru, post wraca w kolejnym przebiegu
- [x] 4.5 Praca bez skonfigurowanego modelu jako stan wspierany, widoczny w stanie modułu
- [x] 4.6 Testy na atrapie modelu: stempel, nadpisanie, odmowa modelu, brak konfiguracji, ograniczenie do okna

## 5. Kontrakt REST

- [x] 5.1 `contract.py` — kształty odpowiedzi; pola odczytu zawsze obecne, puste gdy odczytu nie ma
- [x] 5.2 `routers/posts.py` — okno „ostatnie N godzin", okno jawne, zawężenia po źródle, ocenie i temacie, odczyt jednego posta
- [x] 5.3 `routers/meta.py` — stan modułu: ostatni zbiór, początek zbioru, czynne źródła, czy model skonfigurowany
- [x] 5.4 Odmowa z powodem dla okna bez sensu i zawężenia spoza zakresu
- [x] 5.5 `openapi.py` — druk dokumentu bez serwera i bez bazy
- [x] 5.6 Testy: jeden przez HTTP na dojście stanu do drutu, jedna odmowa, `test_openapi`

## 6. Narzędzia i dostęp

- [ ] 6.1 `mcp_app.py` i cztery narzędzia: ostatnie posty, okno, jeden post, stan archiwum
- [ ] 6.2 Skrót treści na listach, pełna treść wyłącznie przez odczyt jednego posta, tłumaczenie tylko na żądanie
- [ ] 6.3 Test odmawiający zestawowi narzędzia zmieniającego stan oraz test budżetu opisów
- [ ] 6.4 `caller_access.py` — zapis trasa po trasie, odmowa dla ścieżki spoza zapisu, identyfikator aplikacji z tokena, pusty zapis odmawia wszystkim
- [ ] 6.5 Testy dostępu: wołający narzędzi nie wchodzi na REST, brak tożsamości odmawiany, `/health` bez tożsamości

## 7. Workbench

- [ ] 7.1 `SOCIAL_MCP_URL` i `SOCIAL_MCP_SCOPE` w `workbench/config.py` i `.env.example` — oba albo żaden, nieobecność wspierana
- [ ] 7.2 Rejestracja czwartego serwera narzędzi; test, że brak ustawienia nie odbiera rozmowie mowy

## 8. Terminal

- [ ] 8.1 Nowe źródło w `scripts/contract.mjs` → `src/data/contract.social.generated.ts`, `pnpm contract:generate`
- [ ] 8.2 `src/data/config.ts` — baza adresu modułu, wpięcie w stan źródeł
- [ ] 8.3 `src/social/api.ts` i `impact.ts` (podział po progu, porządek) z testami jednostkowymi
- [ ] 8.4 `src/social/SocialView.tsx` i karta posta: okno i licznik, wysoki wpływ na wierzchu, reszta pod rozwinięciem z liczbą
- [ ] 8.5 Stany ekranu: pusto, archiwum nieświeże, model nieskonfigurowany, nieudane odświeżenie nie kasuje listy
- [ ] 8.6 Wpis w rejestrze zakładek; testy widoku (szczęśliwa ścieżka, jeden błąd, jedna odmowa)

## 9. Pocket

- [ ] 9.1 Nowe źródło w `scripts/contract.mjs` i `pnpm contract:generate`
- [ ] 9.2 Adres modułu w `src/data/config.ts`, proxy w `vite.config.ts`, zakres Entra dla trzeciej tożsamości
- [ ] 9.3 `src/social/PostsScreen.tsx` — lista zwinięta, ocena jako `Pill`, odświeżanie gestem przez istniejące `pull.ts`
- [ ] 9.4 Trzecia zakładka w rejestrze i w `App.tsx`; odpytywanie wstrzymane, gdy ekran jest niewidoczny
- [ ] 9.5 Testy ekranu i zapamiętanej zakładki

## 10. Stack lokalny, CI, dokumentacja

- [ ] 10.1 Rola i baza `social` w `compose.yaml` i w tworzeniu baz przez skrypty dev
- [ ] 10.2 Wiersz usługi w `scripts/dev.py` (port 8090, `/health`, powód i miejsce w kolejności startu)
- [ ] 10.3 `checks.yml` — job modułu; zmiana `social_data/contract.py` odpala joby terminala i pocketa
- [ ] 10.4 `CLAUDE.md` — wiersz w tabeli modułów, zdanie o portach, czwarty `*_MCP_URL`
- [ ] 10.5 `docs/architecture.md` — moduł na rysunku i w tekście

## 11. Infrastruktura i wdrożenie

- [ ] 11.1 Terraform: App Service, baza, rejestracja Entra, `allowed_applications` i `TOOL_CALLER_APPLICATION_IDS` z tożsamością workbencha
- [ ] 11.2 `deploy-social-data.yml` nad `_deploy-app-service.yml`, zakończony sondą wdrożenia na `/health`
- [ ] 11.3 Adresy modułu w konfiguracji terminala i pocketa we wdrożeniu
- [ ] 11.4 Przejść kolejność z `design.md` — Migration Plan: ownership, `apply`, obraz, dopiero `SOCIAL_MCP_URL`
