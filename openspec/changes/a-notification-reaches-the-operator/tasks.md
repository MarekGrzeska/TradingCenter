## 1. Szkielet modułu

- [x] 1.1 Założyć `modules/telegram-gateway/` z `pyproject.toml`, `.env.example` i `README.md` (Dockerfile przeniesiony do 9.3: `test_deploy_workflows.py` wymaga, by moduł z obrazem miał workflow deploya)
- [x] 1.2 `config.py` — ustawienia, dwa tryby połączenia z bazą i odmowy startu w kształcie `polymarket_data/config.py`
- [x] 1.3 `app.py` — `lifespan` z pulą `min_size=1, max_size=4`, migracją pod własnym kluczem blokady i weryfikacją wersji schematu
- [x] 1.4 Trasa żywotności odpowiadająca bez bazy i bez Telegrama

## 2. Baza

- [x] 2.1 Migracja `0001`: `bots`, `destinations`, `binding_nonces`, `update_offsets`
- [x] 2.2 `store.py` — wszystkie zapytania modułu, bez ORM
- [x] 2.3 Test: token bota nie jest zwracany przez żadną funkcję odczytową składu

## 3. Wysyłka

- [x] 3.1 Klient Bot API za protokołem, z fake'iem do testów
- [x] 3.2 Wysłanie adresowane nazwą, z odmową dla nazwy nieznanej
- [x] 3.3 Odwzorowanie odmów Telegrama: limit tempa z czasem oczekiwania, blokada bota, pozostałe
- [x] 3.4 Odmowa dla treści przekraczającej sufit Telegrama, bez skracania
- [x] 3.5 Test: adres żądania do Telegrama nie trafia do logu w żadnej ścieżce błędu

## 4. Adresaci i wiązanie

- [x] 4.1 Wydanie odnośnika startowego z jednorazowym sekretem i terminem ważności
- [x] 4.2 Pętla `getUpdates` w tle, per bot, z przesunięciem trzymanym w bazie
- [x] 4.3 Związanie adresata z komendy startowej niosącej sekret; zużycie sekretu
- [x] 4.4 Oznaczenie adresata zablokowanego i odmowa dalszych wysyłek do niego
- [x] 4.5 Usunięcie adresata bez ruszania bota

## 5. Zakładanie botów

- [x] 5.1 Klient bota-twórcy za protokołem (Telethon), z fake'iem do testów
- [x] 5.2 Sesja konta jako ustawienie opcjonalne; odmowa nazywająca brak, gdy jej nie ma
- [x] 5.3 Sprawdzenie sufitu liczby botów przed odezwaniem się do bota-twórcy
- [x] 5.4 Rozpoznanie tokenu po kształcie; odpowiedź bez tokenu jako odmowa oddająca treść
- [x] 5.5 Kasowanie bota tą samą drogą
- [x] 5.6 Test: token nie wychodzi żadną trasą ani do logu, także tuż po założeniu

## 6. Powierzchnia REST

- [x] 6.1 `contract.py` — modele odpowiedzi, żadna nie niesie tokenu
- [x] 6.2 Trasy wysyłki
- [x] 6.3 Trasy zarządzania botami i adresatami
- [x] 6.4 Trasa stanu: sesja konta, liczba botów, liczba adresatów
- [x] 6.5 `openapi.py` — wydanie dokumentu, jak w pozostałych modułach

## 7. Powierzchnia MCP

- [x] 7.1 `mcp_app.py` — montaż `/mcp` i sesja narzędziowa w `lifespan`
- [x] 7.2 Narzędzie wysyłające i narzędzie wyliczające adresatów
- [x] 7.3 Odmowa narzędzia, gdy brama nie zna żadnego adresata
- [x] 7.4 Test: powierzchnia narzędziowa nie zawiera zakładania, kasowania ani wiązania

## 8. Dostęp wywołujących

- [x] 8.1 `caller_access.py` — middleware przed routingiem, tożsamość z roszczenia aplikacji
- [x] 8.2 Rozłączne listy dla powierzchni narzędziowej i kontraktu REST
- [x] 8.3 Test: trasa dodana bez osobnej obsługi też odmawia nieznanemu wywołującemu

## 9. Stos deweloperski i CI

- [x] 9.1 Wiersz usługi w `scripts/dev.py` (port 8100), rola i baza `telegram` w `LOGICAL_DATABASES`
- [x] 9.2 Job modułu w `.github/workflows/checks.yml`
- [x] 9.3 `Dockerfile` **i** `.github/workflows/deploy-telegram-gateway.yml` z sondą wdrożenia — razem, bo test trzyma je parą

## 10. Infrastruktura

- [x] 10.1 App Service, baza `telegram`, rejestracja Entra i Easy Auth w `infra/app-service.tf`
- [x] 10.2 `TOOL_CALLER_APPLICATION_IDS` (workbench) i `REST_CALLER_APPLICATION_IDS` (social-data, strategy) plus `allowed_applications`
- [x] 10.3 Sekrety w Key Vault: `api_id`, `api_hash`, string sesji

## 11. Wywołujący: workbench

- [ ] 11.1 Piąta para `TELEGRAM_MCP_URL` / `_SCOPE` w `workbench/config.py` i `.env.example`
- [ ] 11.2 Test: brak pary zostawia workbench bez tych narzędzi i nie wywraca startu

## 12. Wywołujący: social-data

- [ ] 12.1 Migracja dokładająca znacznik „już powiedziane" przy poście
- [ ] 12.2 Klient bramy w kształcie `strategy/archive.py`, z tożsamością zarządzaną
- [ ] 12.3 Próg oceny wpływu jako ustawienie; wysyłka po zbiórce, znacznik po powodzeniu
- [ ] 12.4 Test: brak adresu bramy zostawia zbiórkę nietkniętą
- [ ] 12.5 Test: nieudana wysyłka nie stawia znacznika, a następny przebieg ponawia

## 13. Wywołujący: strategy

- [ ] 13.1 Migracja dokładająca znacznik przy decyzji
- [ ] 13.2 Klient bramy i ustawienia adresu ze scope'em
- [ ] 13.3 Powiadomienie wyłącznie o decyzji wskazującej zagranie i wyłącznie przy zmianie względem poprzedniej
- [ ] 13.4 Test: brak adresu bramy nie wpływa na decyzję ani na wynik przebiegu

## 14. Dokumentacja

- [ ] 14.1 `README.md` modułu: dwie powierzchnie Telegrama, sesja opcjonalna, sufit botów, limity tempa
- [ ] 14.2 `CLAUDE.md` — zdanie o portach i piąty `*_MCP_URL` (wiersz w tabeli już jest; zostało 57 znaków do sufitu, więc trzeba go podnieść świadomie)
- [ ] 14.3 `docs/architecture.md` — moduł i jego miejsce wśród wywołujących

## 15. Wdrożenie

- [ ] 15.1 `scripts/grant-schema-ownership.sql` na bazie `telegram` — jednorazowo, operator
- [ ] 15.2 `apply` przed obrazami wywołujących; potwierdzić, że ustawienia dojechały przed obrazem
- [ ] 15.3 Założyć pierwszego bota i związać pierwszego adresata przez kontrakt REST
- [ ] 15.4 Sprawdzić wycofanie: wyczyszczenie adresu bramy u wywołującego i restart zostawia go milczącym, ale działającym
