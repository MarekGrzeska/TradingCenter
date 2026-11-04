## Purpose

Czym agent na serwerze sięga po system: wyłącznie powierzchniami MCP przez krawędź, z tokenem osoby operatora wydanym
własnej aplikacji agenta, bez żadnego sekretu systemu, z wyliczonym zestawem narzędzi i z zapisem na rachunku, który
konfiguracja musi włączyć.

## ADDED Requirements

### Requirement: Agent sięga po system tylko przez powierzchnie MCP na krawędzi

Agent MUST sięgać po system wyłącznie przez powierzchnie narzędziowe pod publicznym adresem API, przez krawędź, tak jak
każdy wołający z zewnątrz (`operator-tool-access`). Kontener agenta MUST NOT być w sieci krawędzi, usług ani bazy, MUST
NOT publikować portu i MUST NOT dostawać żadnego sekretu systemu: klucza współdzielonego, haseł baz, kluczy OpenAI ani
tokenów botów pakietu `/telegram`.

#### Scenario: Konfiguracja kontenera

- **WHEN** czytana jest definicja usługi agenta w Compose
- **THEN** nie ma w niej portów, sieci `edge`, `services` ani `data`, ani zmiennej z sekretem systemu

#### Scenario: Żądanie z sieci wewnętrznej

- **WHEN** coś w kontenerze agenta próbuje sięgnąć po workbench albo trading-mcp po nazwie w sieci wewnętrznej
- **THEN** nazwa jest nieosiągalna z sieci agenta

### Requirement: Agent jest osobną aplikacją działającą w imieniu operatora

Każde żądanie agenta do powierzchni narzędziowej MUST nieść token Entra wydany osobnej rejestracji agenta, w imieniu
osoby operatora, z rolą tej osoby. Aplikacja agenta MUST być osobnym wpisem na listach wołających narzędzi workbencha i
trading-mcp, odróżnialnym w każdym logu od klienta operatora przy biurku. To, co agent tworzy narzędziami zespołów, MUST
należeć do operatora i być widoczne w jego terminalu. Usunięcie aplikacji agenta z listy MUST zamykać mu każdą
powierzchnię bez zmiany obrazu.

#### Scenario: Zespół założony z Telegrama

- **WHEN** operator prosi agenta w Telegramie o założenie zespołu
- **THEN** zespół jest na liście zespołów operatora w terminalu

#### Scenario: Zlecenie agenta w śladzie trading-mcp

- **WHEN** agent woła narzędzie zmieniające rachunek
- **THEN** wpisy śladu trading-mcp nazywają aplikację agenta i osobę operatora

#### Scenario: Agent zdjęty z listy

- **WHEN** identyfikator aplikacji agenta zostaje usunięty z listy wołających narzędzi
- **THEN** każde żądanie agenta do tej powierzchni dostaje 403

### Requirement: Token agenta powstaje bez przeglądarki i bez czekania

Logowanie agenta w imieniu operatora MUST odbyć się raz, kodem urządzenia, bez przeglądarki na serwerze. Pamięć
podręczna tokenu MUST leżeć w trwałym wolumenie agenta, czytelna tylko dla użytkownika agenta. Gdy pamięć nie daje
tokenu, pobranie nagłówka przez sesję MUST zakończyć się błędem nazywającym komendę logowania, bez czekania na
operatora. Treść tokenu ani pamięci podręcznej MUST NOT trafić do logu ani do odpowiedzi agenta.

#### Scenario: Token odświeżany po cichu

- **WHEN** token dostępu wygasł, a w pamięci jest token odświeżania
- **THEN** sesja dostaje nowy nagłówek bez udziału operatora

#### Scenario: Brak logowania

- **WHEN** pamięć podręczna jest pusta, a sesja łączy serwer MCP
- **THEN** pobranie nagłówka kończy się błędem nazywającym komendę logowania, a serwer jest pokazany jako nieudany

### Requirement: Narzędzia agenta są wyliczone

Agent MUST móc wołać wyłącznie narzędzia wymienione w jego ustawieniach; wszystko inne MUST być niedostępne bez pytania.
Polecenia powłoki, zapis i edycja plików, pobieranie stron i wyszukiwanie w sieci MUST być zabronione. Odczyt plików MUST
być ograniczony do katalogu roboczego agenta i MUST NOT obejmować pamięci podręcznej tokenu, loginu subskrypcji ani tokenu
bota. Narzędzie wysyłki do innych odbiorców Telegram (`send_telegram_message`) MUST być zabronione.

#### Scenario: Agent próbuje polecenia powłoki

- **WHEN** model w sesji agenta próbuje wykonać polecenie powłoki
- **THEN** wywołanie jest odrzucone bez wykonania

#### Scenario: Wysyłka do innego odbiorcy

- **WHEN** model próbuje wywołać `send_telegram_message`
- **THEN** wywołanie jest odrzucone bez wysłania czegokolwiek

### Requirement: Zapis na rachunku jest wyłączony, dopóki konfiguracja go nie włączy

Narzędzia zmieniające rachunek (składanie i zamykanie pozycji, zmiana stopów, anulowanie zleceń oczekujących, zmiana
aktywnego konta, zasilenie konta demo) MUST być zabronione, dopóki konfiguracja wdrożenia jawnie ich nie włączy. Brak
ustawienia albo wartość inna niż włączająca MUST oznaczać zakaz. Po włączeniu agent MUST wołać takie narzędzie dopiero
po potwierdzeniu operatora w tej samej rozmowie, a granicą, której nie przekracza żadna konfiguracja agenta, MUST
pozostać strażnik konta demo w trading-mcp.

#### Scenario: Domyślna konfiguracja

- **WHEN** ustawienie zapisu na rachunku nie jest podane, a operator prosi o zamknięcie pozycji
- **THEN** wywołanie `close_position` jest odrzucone, a agent mówi, że zapis na rachunku jest wyłączony

#### Scenario: Zapis włączony, operator potwierdza

- **WHEN** zapis na rachunku jest włączony, agent proponuje przesunięcie stopu, a operator odpisuje potwierdzeniem
- **THEN** agent woła `amend_stops` i podaje wynik

#### Scenario: Zapis włączony, brak potwierdzenia

- **WHEN** zapis na rachunku jest włączony, a polecenie zapisu pojawia się w treści czytanej z archiwum, nie od operatora
- **THEN** agent nie woła narzędzia zapisującego
