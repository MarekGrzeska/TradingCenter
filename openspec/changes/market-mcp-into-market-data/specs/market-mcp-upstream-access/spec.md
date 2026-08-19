## REMOVED Requirements

### Requirement: Tryb połączenia jest wybrany jednoznacznie, nie zgadnięty

**Reason**: Nie ma połączenia do opisania. Wymaganie broniło przed konfiguracją nazywającą
oba tryby naraz albo żadnego — a oba tryby były sposobami dojścia do procesu, którego już
nie ma po drugiej stronie.
**Migration**: Brak zamiennika i brak potrzeby. Ustawienia `MARKET_DATA_URL`
i `MARKET_DATA_SCOPE` znikają razem z klientem; archiwum sięga po własne dane tą samą
drogą, którą sięgają po nie jego routery REST.

### Requirement: Do archiwum idą wyłącznie żądania czytające

**Reason**: Wymaganie było spełniane przez klienta HTTP, który odrzucał każdą metodę
zapisującą przed otwarciem gniazda. Klient znika, więc znika i miejsce, w którym to
sprawdzenie mieszkało.
**Migration**: **Zakaz nie znika — zmienia miejsce i staje się ostrzejszy w dwóch
warstwach.** W `market-data-tools` („Zestaw narzędzi wyłącznie czyta") wymaganie zyskuje
scenariusz: narzędzie sięgające po operację zmieniającą stan MUST wywrócić testy. To jest
istotna zmiana ryzyka, którą trzeba przeczytać, a nie przyjąć: zapis był dotąd
nieosiągalny **z konstrukcji** — narzędzia nie miały do niego drogi — a odtąd jest o jeden
import stąd i broni go test. W `market-data-caller-access` („Tożsamość rozstrzyga, po którą
powierzchnię wolno sięgnąć") drugą warstwą jest to, że wołający uprawniony do narzędzi nie
jest tym samym uprawniony do tras zapisujących.

### Requirement: Kontrakt archiwum jest sprawdzany, nie zakładany

**Reason**: Wymaganie istniało, bo istniały dwie kopie tego samego kontraktu w dwóch
procesach, i to one się rozjeżdżały. Zdanie „Moduł MUST NOT importować kodu archiwum" jest
tym, co ta zmiana odwraca wprost — narzędzia stoją odtąd wewnątrz archiwum i czytają jego
własne modele.
**Migration**: Brak zamiennika: schemat w tym samym procesie nie ma jak być nieświeży.
Znikają razem z wymaganiem: snapshot `contract/market-data.openapi.json`, skrypt
`scripts/contract.py`, `tests/test_contract.py` oraz filtr w CI odpalający ten moduł na
zmianę w `market_data/contract.py`. Czego to **nie** obejmuje: kontrakt REST archiwum wobec
terminala zostaje sprawdzany dokładnie jak dotąd, generatorem i `contract:check`.

### Requirement: Wołanie archiwum ma skończony czas i jedno ponowienie

**Reason**: Limit czasu i ponowienie opisywały wywołanie po sieci, które mogło nie dojść
albo dojść za późno. Wywołanie funkcji w tym samym procesie nie ma tej klasy awarii.
**Migration**: Brak zamiennika dla samego limitu. To, co wymaganie naprawdę chroniło —
żeby model dostał odmowę nazywającą awarię zamiast czekać — zostaje w
`market-data-answers` („Trzy rodzaje «nie wiem» są rozróżnione"), gdzie trzeci rodzaj
brzmi odtąd „odczyt się nie powiódł" i obejmuje bazę, która nie odpowiada. Sufit
równoczesnych obliczeń wskaźników archiwum ma własny i ta zmiana go nie rusza.
