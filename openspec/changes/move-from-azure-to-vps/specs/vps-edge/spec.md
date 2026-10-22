## Purpose

Co stoi między internetem a systemem na serwerze: szyfrowanie, które trasy są publiczne, jak aplikacja
odróżnia żądanie z zewnątrz od wywołania innej usługi i co nie ma portu na zewnątrz wcale.

## ADDED Requirements

### Requirement: Jedno wejście z szyfrowaniem

Jedynym procesem nasłuchującym na portach publicznych serwera MUST być reverse proxy. Ruch HTTP MUST
być przekierowany na HTTPS z ważnym certyfikatem dla domeny systemu, odnawianym automatycznie.
Aplikacje i baza MUST NOT publikować portów na hoście.

#### Scenario: Ktoś publikuje port aplikacji

- **WHEN** plik Compose przypisuje port hosta usłudze innej niż proxy
- **THEN** test w repozytorium odrzuca zmianę

#### Scenario: Wejście przez HTTP

- **WHEN** przychodzi żądanie HTTP na domenę systemu
- **THEN** proxy odpowiada przekierowaniem na HTTPS

### Requirement: Krawędź oznacza żądania z zewnątrz i usuwa obce nagłówki tożsamości

Proxy MUST dopisywać każdemu przekazywanemu żądaniu nagłówek krawędzi, nadpisując wartość, która
przyszła z zewnątrz, i MUST usuwać nagłówki `X-MS-CLIENT-PRINCIPAL*`. Aplikacja MUST traktować żądanie z
nagłówkiem krawędzi jako przychodzące z zewnątrz (wymaga ważnego tokenu), a bez niego jako wywołanie z
sieci wewnętrznej (wymaga klucza usługi).

#### Scenario: Podrobiony nagłówek krawędzi z zewnątrz

- **WHEN** klient z internetu wysyła żądanie z własną wartością nagłówka krawędzi
- **THEN** aplikacja dostaje wartość ustawioną przez proxy, a żądanie traktuje jako zewnętrzne

### Requirement: Usługi i baza rozmawiają siecią wewnętrzną

Wywołania między usługami systemu i połączenia z bazą MUST odbywać się siecią wewnętrzną kontenerów,
z pominięciem proxy. Adresy usług w ustawieniach MUST wskazywać nazwy w tej sieci, nie domenę publiczną.

#### Scenario: Workbench łączy się z bazą i gatewayem

- **WHEN** workbench startuje na serwerze
- **THEN** łączy się z bazą i z gatewayem po nazwach w sieci wewnętrznej, z pominięciem proxy
