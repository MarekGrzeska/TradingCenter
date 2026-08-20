## 1. Gateway: drugie poświadczenie

- [x] 1.1 `config.py`: `BROWSER_CALLER_APPLICATION_IDS`, pusta lista lokalnie (D3)
- [x] 1.2 Odczyt aplikacji wołającej z oświadczeń tokenu (`azp`/`appid`), nie z nagłówka
      nazywającego osobę (D3)
- [x] 1.3 `RequireGatewayKey` → klucz **albo** rozpoznana aplikacja; brak obu to nadal `401`
- [x] 1.4 Testy: żądanie z kluczem jak dotąd; żądanie z rozpoznaną aplikacją bez klucza
      przechodzi; z nierozpoznaną — `401`; bez niczego — `401`

## 2. Gateway: rejestr tras

- [x] 2.1 Lista tras dostępnych wołającemu z przeglądarki: konta, przełączenie, korekta
      salda, pozycje, zlecenia oczekujące (D4)
- [x] 2.2 Każda inna trasa — odmowa dla tego wołającego, w tym strumień
- [x] 2.3 Testy: terminal czyta konta; terminal składający zlecenie dostaje odmowę przed
      dotknięciem providera; trasa spoza rejestru jest odmawiana domyślnie

## 3. Terminal: klient i ekran

- [x] 3.1 `src/data/config.ts` i `.env.example`: adres gatewaya, ścieżka względna w dev
- [x] 3.2 `vite.config.ts`: proxy `/gateway` z nagłówkiem klucza po stronie serwera dev (D5)
- [x] 3.3 `src/accounts/gatewayApi.ts`: konta, pozycje, przełączenie, korekta salda —
      z mapowaniem na kształt terminala, jak w `archive.ts`
- [x] 3.4 `src/accounts/AccountsView.tsx`: konta, pozycje konta aktywnego, ostatni udany
      odczyt, odmowa powiedziana wprost
- [x] 3.5 Doładowanie: formularz kwoty, kwota ujemna dozwolona, saldo po zmianie bez
      odświeżania ręcznego
- [x] 3.6 Przełączenie konta z ostrzeżeniem o zerwanym strumieniu **przed** wykonaniem
- [x] 3.7 Zakładka w `app/tabs.ts` i trasa

## 4. Terminal: odświeżanie

- [x] 4.1 Jeden takt na konta i pozycje, tylko gdy zakładka jest widoczna (D6)
- [x] 4.2 Testy: stan zmieniony po stronie modułu pojawia się bez przeładowania; nieudany
      odczyt nie kasuje ostatniego znanego stanu i jest powiedziany

## 5. Infrastruktura (apply operatora)

- [x] 5.1 `infra/app-service.tf`: `module "capital_gateway_easy_auth"`, `auth_settings_v2`
      z `AllowAnonymous` (D1), terminal na liście wpuszczanych
- [x] 5.2 Zdjęcie reguł adresowych jako drzwi, z komentarzem nazywającym cenę (D2)
- [x] 5.3 `BROWSER_CALLER_APPLICATION_IDS` w ustawieniach aplikacji
- [x] 5.4 `terraform fmt -check` i `validate` przechodzą (job `infra` w CI)

## 6. Domknięcie

- [x] 6.1 `uv run pytest`, `ruff`, `pyright` w `capital-gateway`
- [x] 6.2 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `terminal`
- [x] 6.3 `uv run python scripts/contract.py check` w `trading-mcp` — snapshot gatewaya
- [x] 6.4 `openspec validate accounts-screen-opens-the-gateway --strict`
- [x] 6.5 `review.md` — co się okazało przy dwóch postaciach poświadczenia i czego nie
      dało się sprawdzić bez apply
