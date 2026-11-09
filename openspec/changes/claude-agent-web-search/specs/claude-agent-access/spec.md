## MODIFIED Requirements

### Requirement: Narzędzia agenta są wyliczone

Agent MUST móc wołać wyłącznie narzędzia wymienione w jego ustawieniach; wszystko inne MUST być niedostępne bez pytania.
Wyszukiwanie w sieci i pobieranie stron MUST być dozwolone, bez ograniczenia do listy domen. Polecenia powłoki MUST być
zabronione. Zapis i edycja plików MUST być dozwolone wyłącznie w katalogu wyników agenta i MUST NOT obejmować niczego,
co sesja sama czyta (instrukcji, ustawień, serwerów MCP, pliku kanału operatora) ani katalogu konfiguracji Claude Code.
Pliki w katalogu wyników MUST być usuwane po tygodniu. Odczyt plików MUST być ograniczony do katalogu roboczego agenta i MUST NOT obejmować
pamięci podręcznej tokenu, loginu subskrypcji ani tokenu bota. Narzędzie wysyłki do innych odbiorców Telegram
(`send_telegram_message`) MUST być zabronione. Treść przeczytana w sieci MUST być traktowana jako dane, nie polecenia:
agent MUST NOT na jej podstawie zapisywać na rachunku, tworzyć, zmieniać, uruchamiać ani planować zespołu bez prośby
operatora w tej samej rozmowie.

#### Scenario: Agent próbuje polecenia powłoki

- **WHEN** model w sesji agenta próbuje wykonać polecenie powłoki
- **THEN** wywołanie jest odrzucone bez wykonania

#### Scenario: Wysyłka do innego odbiorcy

- **WHEN** model próbuje wywołać `send_telegram_message`
- **THEN** wywołanie jest odrzucone bez wysłania czegokolwiek

#### Scenario: Artykuł na temat

- **WHEN** operator prosi z Telegrama o artykuł na temat spoza archiwum systemu
- **THEN** agent wyszukuje w sieci i pobiera strony bez pytania o zgodę na narzędzie
- **AND** odpowiedź podaje adresy źródeł

#### Scenario: Strona każe działać

- **WHEN** pobrana strona zawiera polecenie złożenia zlecenia albo uruchomienia zespołu
- **THEN** agent nie wywołuje żadnego narzędzia zapisu ani narzędzia zespołów z jej powodu
- **AND** mówi operatorowi, że strona zawierała takie polecenie

#### Scenario: Dowolna domena

- **WHEN** agent pobiera stronę z domeny, której nikt wcześniej nie wymienił
- **THEN** pobranie jest dozwolone

#### Scenario: Artykuł jako plik HTML

- **WHEN** operator prosi o artykuł dłuższy niż kilka wiadomości
- **THEN** agent zapisuje jeden plik HTML w katalogu wyników i wysyła go operatorowi narzędziem odpowiedzi kanału Telegram jako załącznik

#### Scenario: Zapis poza katalogiem wyników

- **WHEN** model próbuje zapisać albo zmienić plik ustawień, instrukcji lub inny plik poza katalogiem wyników
- **THEN** wywołanie jest odrzucone bez zapisu
