## Context

Motywacja: `proposal.md` — Why. Dobór usług, ceny i alternatywy odrzucone na poziomie rachunku:
`docs/azure-infrastructure-proposal.html`. Warunki brzegowe, które kształtują to rozwiązanie:

- **Subskrypcja jest pusta.** Nie ma na czym stanąć, więc plan musi rozwiązać także problem stanu
  Terraforma, zanim cokolwiek innego powstanie.
- **Darmowy roczny limit obejmuje 750 godzin _jednej_ instancji `B_Standard_B1ms` z 32 GB.**
  Osobne środowisko przejściowe przekracza go natychmiast.
- **capital.com liczy limit żądań na konto, nie na proces.** Druga instancja gatewaya to drugi
  `RateGate` i podwójny ruch do brokera.
- **Usługi chodzą bez przerwy.** To przesądza o modelu rozliczenia — patrz decyzja o App Service.
- **Konfigurację połączenia trzyma plik `.env` na maszynie dewelopera.** Wszystko, co da się w nim
  przestawić, kiedyś zostanie przestawione — łącznie z adresem bazy.
- **Testy `market-data` są testami schematu.** `tests/conftest.py` robi `TRUNCATE` na wszystkich
  tabelach między przypadkami.

## Goals / Non-Goals

**Goals:**

- Cała infrastruktura daje się zastosować od zera na pustej subskrypcji, bez kroku klikanego
  w portalu.
- Wdrożenie każdego modułu wyzwala się z `main` i nie wymaga żadnego przechowywanego sekretu do
  Azure.
- Endpointy handlowe wymagają uwierzytelnienia w kodzie, niezależnie od konfiguracji platformy.
- Żaden trwały sekret nie ląduje na dysku dewelopera ani w repozytorium.

**Non-Goals:**

- Wysoka dostępność. Plan `B1` i baza B1ms to pojedyncze instancje; ich awaria zatrzymuje wszystko
  i jest to świadomie zaakceptowane na tym etapie.
- Izolacja sieciowa przez VNet i prywatny endpoint bazy. Reguła firewalla na adresy IP wystarcza.
- Środowisko przejściowe. Jedno środowisko, bo drugie kosztuje darmowy rok bazy.
- Autoryzacja rozumiana jako role i uprawnienia wewnątrz aplikacji. Tu chodzi o uwierzytelnienie:
  wywołujący jest znany albo nie ma wstępu.

## Decisions

### App Service, nie Container Apps

Container Apps rozliczają sekundy procesora — model pod obciążenia zrywowe. Te usługi chodzą non
stop, więc dwa kontenery po 0,25 vCPU wychodzą drożej niż cały plan `B1` dzielony przez obie
aplikacje. Szczegóły rachunku: dokument, sekcja 2.

Konsekwencja, którą trzeba nieść dalej: plan `Basic` daje **350 równoczesnych połączeń WebSocket na
instancję**, a obsługę WebSocketów trzeba włączyć jawnie (`websockets_enabled = true`). Przy jednym
operatorze i siatce sześciu wykresów zapas jest dwurzędowy.

### Gateway ma dokładnie jedną instancję

`worker_count = 1` i **żadnego autoskalowania**. Druga instancja to drugi `RateGate` i przekroczony
limit dziesięciu żądań na sekundę, objawiający się wywołującemu jak problem z danymi, a nie jak
problem z ruchem. To jest reguła, którą ktoś kiedyś „poprawi" w dobrej wierze, więc MUST być
opatrzona komentarzem w kodzie Terraforma.

### Uwierzytelnianie gatewaya w kodzie, nie w konfiguracji platformy

Ograniczenia dostępu App Service zostają — ale jako warstwa druga. Pierwszą jest kod, bo
konfigurację psuje jeden błędny wpis, a jej zepsucie nie jest niczym widoczne. Stąd też wymaganie,
że **moduł bez skonfigurowanego poświadczenia nie wstaje**: gdyby wstawał, brak konfiguracji
objawiłby się otwartym endpointem handlowym, czyli niczym.

Alternatywa odrzucona: Easy Auth (Entra ID) także przed gatewayem. Wywołującym gatewaya jest
`market-data`, usługa, nie człowiek; przepuszczanie ruchu maszynowego przez przepływ logowania
przeznaczony dla przeglądarki dokłada ruchomą część do najbardziej wrażliwej ścieżki. Easy Auth
zostaje tam, gdzie po drugiej stronie jest przeglądarka — przed `market-data`.

Wybór konkretnego mechanizmu (klucz współdzielony w nagłówku kontra token tożsamości zarządzanej)
to pytanie otwarte — patrz niżej. Specyfikacja opisuje zachowanie obserwowalne, które obie opcje
spełniają identycznie.

### Terminal osiąga katalog instrumentów przez `market-data`, nigdy bezpośrednio przez gateway

Dziś `terminal` woła gateway wprost z przeglądarki po katalog instrumentów — [gatewaySource.ts](modules/terminal/src/data/gatewaySource.ts)
i `vite.config.ts` (`GATEWAY_PROXY_TARGET`, z komentarzem wprost mówiącym o czymś, co w produkcji
stoi przed obiema usługami). Ten kształt nie da się pogodzić z gatewayem niepublicznym: gdyby gateway
odrzucał ruch spoza planu App Service, przeglądarka nie dobiłaby do niego wcale; gdyby miał
przepuszczać ruch z przeglądarki, potrzebowałby klucza po stronie klienta — a klucz w kodzie
przeglądarki jest jawny dla każdego, kto otworzy narzędzia deweloperskie. Nie jest to sprzeczność
wykryta na etapie infrastruktury: `docs/azure-infrastructure-proposal.html` (sekcja 5) od początku
zakładał gateway niepubliczny i `market-data` publiczny za Easy Auth — to kod terminala nie dogonił
tego założenia.

Rozwiązanie: `market-data` zyskuje trasy proxujące katalog instrumentów, wołane własnym,
już istniejącym poświadczeniem do gatewaya. `terminal` przestaje mieć osobny adres dla gatewaya
i woła wyłącznie `market-data` — ten sam moduł, z którego i tak czyta świece.

Alternatywa odrzucona: gateway podłączony do Static Web Apps jako „linked backend" z Access
Restrictions dopuszczającym wyłącznie ruch z SWA. Auth byłby wtedy topologią sieci, nie kluczem —
ale to mechanizm specyficzny dla Azure, którego działania nie da się zweryfikować bez stawiania
infrastruktury, i wprowadzałby drugi, odmienny model dostępu do gatewaya obok modelu dla
`market-data`. Jeden model, przez jeden już istniejący moduł pośredniczący, jest prostszy do
utrzymania.

Alternatywa odrzucona: uznanie katalogu instrumentów za dane publiczne i wyłączenie tras
`/instruments*`, `/asset-classes` z wymogu poświadczenia w `capital-access-control`. Zwęża to
gwarancję „każde wywołanie niesie poświadczenie" bez wystarczającego powodu — katalog niesie też
bieżące bid/ask, a dodatkowy przeskok przez `market-data` jest tani.

### Sonda zdrowia jako jedyny wyjątek

App Service odpytuje sondę bez poświadczenia i na tej podstawie restartuje aplikację. Wyjątek jest
więc nieunikniony i dlatego MUST być dokładnie jeden, a sonda MUST NOT ujawniać niczego poza
żywotnością — obecna trasa `/` zwracająca nazwę i wersję modułu wymaga przeglądu pod tym kątem.

### Jeden serwer bazy, dwie bazy logiczne, cztery tożsamości

Rozdział środowisk musi się zmieścić w jednej instancji, bo taki jest darmowy limit. Zostają dwie
bazy — `market_data` i `market_data_dev`.

Ról jest **cztery, nie trzy**, i to jest poprawka wprowadzona dopiero przy wdrażaniu, nie w
pierwotnym projekcie. Administrator Entra przypisany serwerowi w Azure Postgres Flexible Server
**omija każdy `GRANT` na każdej bazie** — to nie jest rola z uprawnieniami, to superużytkownik.
Pierwotny plan zakładał, że osobiste konto operatora (`mgrzeskait@outlook.com`) jest jednocześnie
administratorem *i* tożsamością „deweloperską" czytaną przez `.env`. Przy wdrażaniu okazało się, że
to zerowałoby całą ochronę: administrator i tak dobija do `market_data`, więc GRANT ograniczający
rolę deweloperską do `market_data_dev` nic by nie chronił, gdyby ta rola była tym samym kontem co
administrator.

Rozwiązanie: **administrator zostaje wyłącznie do naprawy awarii i do DBeavera**, nigdy nie jest
poświadczeniem czytanym automatycznie. Tożsamość „deweloperska" to osobny Service Principal
(`sp-tradingcenter-market-data-dev`, `infra/entra.tf`, provider `azuread`) — RW wyłącznie na
`market_data_dev`, `CONNECT` na `market_data` jawnie odebrany. Cztery tożsamości: administrator
(człowiek, pełny dostęp, do awarii i DBeavera), aplikacyjna (tożsamość zarządzana App Service, RW
na `market_data` — tworzona w grupie 5, bo potrzebuje App Service, który jeszcze nie istnieje),
deweloperska (Service Principal, RW na `market_data_dev`), i **nie ma osobnej roli operatorskiej** —
patrz niżej.

**Konsekwencja zaakceptowana wprost**: skoro DBeaver łączy się kontem administratora, `SELECT`-only
dla operatora — opisane w `docs/dbeaver-azure-connection.html` jako osobna, czwarta tożsamość — nie
jest egzekwowalne wobec tego samego mechanizmu, który zezwala na wszystko. Dla projektu
jednoosobowego to świadomy kompromis: administrator i tak ma pełny dostęp przez portal Azure, więc
osobna rola tylko do przeglądania danych nie broni przed niczym, przed czym broniłaby się sama
przez się. Rolę operatorską dałoby się odtworzyć jako piątą, osobną tożsamość — nieopłacalne teraz,
możliwe później, jeśli do projektu dołączy ktoś drugi.

Alternatywa odrzucona: jedna rola i rozdział wyłącznie przez nazwę bazy w `.env`. Nazwa w pliku
konfiguracyjnym nie jest zabezpieczeniem — jest konwencją, a konwencja zawodzi dokładnie wtedy, gdy
`alembic upgrade` idzie na archiwum warte dwadzieścia siedem godzin odtwarzania. **Rola deweloperska
bez `CONNECT` na `market_data` czyni ten błąd niewykonalnym**, zamiast czynić go niezalecanym — pod
warunkiem, że rola deweloperska nie jest też administratorem, co jest właśnie tym, co ta poprawka
naprawia.

Alternatywa odrzucona: dwa schematy w jednej bazie. Migracje operują na schemacie domyślnym;
drugi schemat komplikuje każdą przyszłą migrację.

### Do bazy — tożsamość, do capital.com — Key Vault

Dwa różne sekrety, dwa różne rozwiązania, bo mają różnych właścicieli.

Poświadczenia capital.com pochodzą od zewnętrznego providera i muszą gdzieś leżeć: Key Vault,
a w ustawieniach aplikacji wyłącznie odwołanie `@Microsoft.KeyVault(SecretUri=...)`. Wartość nie
przechodzi przez kod Terraforma ani przez logi wdrożenia.

Hasło do bazy nie musi istnieć w ogóle, więc nie istnieje: aplikacja łączy się tożsamością
zarządzaną, lokalny proces `market-data` — tożsamością Service Principal poświadczaną sekretem
klienta Entra (patrz „Jeden serwer bazy, dwie bazy logiczne, cztery tożsamości" — **nie** osobistym
kontem dewelopera po `az login`, bo to konto jest administratorem serwera i ominęłoby każdy GRANT).
Gdyby hasło do bazy zostało w Key Vault, po przeniesieniu pracy lokalnej na Azure musiałoby wylądować
w `.env` na laptopie — czyli hasło do serwera produkcyjnego na dysku. Cena tego wyboru to
poświadczenie o ważności — dla tożsamości zarządzanej około godziny, dla Service Principal tyle, ile
ważny jest jego token — które trzeba odnawiać; pobieranie tokenu wpina się w moment nawiązywania
połączenia przez pulę, nie w start procesu.

Do DBeavera i innej pracy ręcznej dewelopera (nie automatycznego procesu) `az login` własnym kontem
zostaje — ale to konto jest administratorem serwera, więc widzi obie bazy z pełnymi prawami. Patrz
wyżej, dlaczego to jest świadomy kompromis, nie przeoczenie.

### Bootstrap osobnym katalogiem ze stanem lokalnym

Stan Terraforma ma leżeć w Blob Storage, ale konto magazynu na ten stan trzeba czymś utworzyć.
`infra/bootstrap/` ze stanem lokalnym tworzy wyłącznie grupę zasobów, konto magazynu i kontener.
Uruchamiany raz; jego stan nie zawiera nic wrażliwego.

### Wdrożenia przez OIDC, obrazy w GHCR

Federacja tożsamości zamiast klucza wdrożeniowego: w repozytorium nie ma **żadnego** sekretu do
Azure. Identyfikatory dzierżawy i subskrypcji idą przez `vars`, nie `secrets` — nie są tajne,
a trzymanie ich jako sekretów tylko sugeruje, że są.

Obrazy tagowane `github.sha`, nie `latest`. Tag ruchomy sprawia, że „co jest wdrożone" przestaje
być pytaniem z odpowiedzią, a wycofanie zmiany przestaje być operacją odwracalną.

Terraform ma własny przepływ: `plan` na pull requestach, `apply` po scaleniu. Zmiana infrastruktury
ma być czytelnym diffem przed zastosowaniem, nie po.

### Firewall bazy na adresy IP

Adresy wyjściowe App Service MUST być czytane z zasobu (`possible_outbound_ip_address_list`), nigdy
wpisywane ręcznie — **zmieniają się przy zmianie warstwy planu**, a przejście z `B1` na `B2` to
scenariusz przewidywany, nie hipotetyczny. Do tego reguła na adres dewelopera, trzymany jako zmienna
w `tfvars`.

### Testy zostają na testcontainers

Wskazanie testów na serwer współdzielony jest wykluczone: `TRUNCATE` między przypadkami skasowałby
archiwum, a dwa równoległe przebiegi w CI kasowałyby się wzajemnie. Osobna baza testowa na tym samym
serwerze nie rozwiązuje drugiego problemu.

Konsekwencja przyjęta świadomie: **Docker przestaje być potrzebny do codziennej pracy i pozostaje
potrzebny do `pytest`**. `scripts/dev.*` przestają go sprawdzać, więc jego brak ujawni się dopiero
przy testach — dlatego komunikat pomijania testów bazodanowych w `conftest.py` pozostaje tym
miejscem, które o Dockerze mówi.

### PostgreSQL 17

Nie 18. TimescaleDB i narzędzia nadganiają nową wersję główną z opóźnieniem, a moduł nie zyskuje nic
na byciu pierwszym.

## Risks / Trade-offs

**Uwierzytelnianie gatewaya psuje jego jedynego konsumenta** → `market-data` przestaje móc go
odpytać w tej samej chwili, w której gateway zaczyna wymagać poświadczenia (`terminal` gatewaya już
nie dotyka — patrz decyzja wyżej). Mitygacja: kolejność zadań stawia `market-data` z gotowym
poświadczeniem przed włączeniem wymogu, a wymóg wchodzi jako ostatni krok tej grupy.

**Ktoś kiedyś ustawi autoskalowanie planu** → podwójny ruch do brokera objawiający się jak problem
z danymi. Mitygacja: komentarz w Terraformie przy `worker_count` i wymaganie opisane w dokumencie;
poza tym nic tego nie powstrzyma, bo Azure nie ma jak wiedzieć, że drugiej instancji być nie może.

**Zmiana warstwy planu zrywa łączność z bazą** → adresy wyjściowe się przestawiają. Mitygacja:
czytanie ich z zasobu, nigdy ręcznie.

**Adres wyjściowy dewelopera się zmienia** → timeout wyglądający jak awaria bazy. Mitygacja: adres
jako zmienna w `tfvars` ze skryptem odświeżającym; naprawa ma trwać minutę, nie godzinę diagnozy.

**Latencja lokalnej pracy rośnie z poniżej milisekundy do 10–20 ms** → uzupełnianie wstecz robi
tysiące rund w obie strony. Zaakceptowane; odpowiedzią, jeśli zacznie przeszkadzać, jest większa
porcja na rundę, nie powrót kontenera.

**Praca bez internetu przestaje być możliwa** → zaakceptowane wprost, bez obejścia.

**Produkcja i praca lokalna dzielą jeden vCPU i 32 GB** → ciężkie zapytanie lokalne konkuruje
z ingestem, a dane deweloperskie zjadają miejsce liczone do darmowego limitu. Mitygacja: alert na
`storage_percent > 80%` i świadomość, że `market_data_dev` wolno wyczyścić w każdej chwili.

**Poświadczenie do bazy wygasa w trakcie długiego uzupełniania wstecz** → najdłuższa operacja modułu
jest najbardziej prawdopodobnym miejscem ujawnienia błędu w odnawianiu. Wymaganie sformułowane tak,
by dało się to sprawdzić testem.

**Rola odcinająca samą siebie od bazy** → naprawialne wyłącznie przez administratora serwera.
Mitygacja: administrator Entra przypisany jawnie w Terraformie, żeby zawsze istniała droga powrotna.

**Restart platformy przerywa strumień** → konserwacja App Service jest normalnym zdarzeniem.
`Upstream` w gatewayu ma pętlę ponawiania, a `market-data` domyka lukę po restarcie — to już jest
w wymaganiach modułów, ale tutaj przestaje być opcjonalne.

**Key Vault ma miękkie usuwanie** → `terraform destroy` zostawia sejf w stanie usuniętym, a ponowne
utworzenie z tą samą nazwą się wywraca. Mitygacja: losowy przyrostek w nazwie.

## Migration Plan

Kolejność jest podyktowana jedną zasadą: **nic nie staje w internecie, zanim endpointy handlowe nie
wymagają uwierzytelnienia**.

1. Uwierzytelnianie w gatewayu i wyłączenie publikacji API na produkcji — w całości lokalnie,
   z testami. Konsumenci dostają poświadczenie **przed** włączeniem wymogu po stronie gatewaya.
2. `infra/bootstrap/` — stan Terraforma. Raz, ze stanem lokalnym.
3. `infra/` z backendem zdalnym: baza, obie bazy logiczne, role, Key Vault, plan, Application
   Insights. Baza pierwsza, bo od niej zależy reszta konfiguracji.
4. Rozłączność uprawnień sprawdzona ręcznie, zanim cokolwiek zacznie z nich korzystać.
5. Federacja OIDC — od tego momentu wdrożenia działają bez hasła.
6. `Dockerfile` gatewaya i pierwsze wdrożenie. Cały łańcuch sprawdzany na module, który już działa.
7. `terminal` na Static Web Apps, ze ścieżkami API względnymi.
8. Przełączenie pracy lokalnej na `market_data_dev`, usunięcie `compose.yaml`.
9. `market-data`: połączenie z bazą, wdrożenie, alerty wraz z metryką wieku najnowszej świecy.

**Rollback**: do punktu 5 włącznie sprowadza się do cofnięcia commitów — infrastruktura może zostać
nietknięta, bo nic produkcyjnego jeszcze od niej nie zależy. Po punkcie 8 rollback pracy lokalnej
oznacza przywrócenie `compose.yaml` i poprzedniego `.env`; dane z lokalnego kontenera są wtedy nadal
na dysku, o ile nie wykonano `docker compose down -v`.

## Open Questions

- **Czym dokładnie `market-data` przedstawia się gatewayowi**: kluczem współdzielonym w nagłówku,
  trzymanym w Key Vault, czy tokenem tożsamości zarządzanej weryfikowanym przez gateway. Klucz jest
  prostszy i wystarcza dla ruchu maszynowego w jednej subskrypcji; token znosi rotację, ale dokłada
  weryfikację po stronie gatewaya. Rozstrzygnięcie nie zmienia żadnego wymagania ze specyfikacji —
  zachowanie obserwowalne jest identyczne — ani podziału zadań; zmienia wyłącznie treść jednego
  zadania w grupie 1.
- Czy DBeaver w edycji Community obsługuje Entra ID dla PostgreSQL-a natywnie, czy token trzeba
  wklejać co godzinę. Dotyczy wyłącznie wygody operatora i treści `docs/dbeaver-azure-connection.html`.
