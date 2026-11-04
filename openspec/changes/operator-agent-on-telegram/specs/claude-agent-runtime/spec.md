## Purpose

Stała sesja Claude Code na serwerze, z którą operator rozmawia z telefonu przez prywatnego bota Telegram: na czym działa
model, kto może do niej pisać, skąd bierze instrukcje i co dzieje się z nią po awarii, w nocy i o stałych porach.

## ADDED Requirements

### Requirement: Agent działa na subskrypcji operatora, nigdy na kluczu API

Agent MUST korzystać z modelu wyłącznie przez login subskrypcji operatora. Proces MUST odmówić startu sesji, gdy w jego
środowisku jest klucz albo token API Anthropic, gdy którykolwiek plik ustawień wskazuje helper klucza API, albo gdy
kontrola tego nie zdołała się wykonać. Odmowa MUST nazywać powód.

#### Scenario: Klucz API w środowisku

- **WHEN** kontener agenta startuje z ustawionym `ANTHROPIC_API_KEY`
- **THEN** sesja nie startuje, a log nazywa zmienną jako powód odmowy

#### Scenario: Czysta konfiguracja

- **WHEN** kontener startuje bez klucza API, helpera klucza i zapisanego klucza
- **THEN** sesja startuje na loginie subskrypcji

### Requirement: Jedna stała sesja, wznawiana po awarii i zaczynana od nowa po nocy

Na serwerze MUST działać dokładnie jedna sesja agenta. Sesja zakończona awarią MUST zostać uruchomiona ponownie z
kontynuacją ostatniej rozmowy. Raz na dobę, w nocy, sesja MUST zostać zakończona i uruchomiona od czystego kontekstu.
Zmiana instrukcji agenta (nowy obraz) MUST oznaczać start od czystego kontekstu, a nie kontynuację rozmowy prowadzonej
pod starymi instrukcjami.

#### Scenario: Proces sesji ginie

- **WHEN** proces Claude Code w sesji kończy się nieoczekiwanie
- **THEN** sesja wraca w ciągu minuty i kontynuuje poprzednią rozmowę

#### Scenario: Nocny restart

- **WHEN** nadchodzi nocna pora restartu
- **THEN** sesja zaczyna od czystego kontekstu

#### Scenario: Wdrożenie z nowymi instrukcjami

- **WHEN** kontener startuje z instrukcjami różnymi od tych, pod którymi toczyła się ostatnia rozmowa
- **THEN** sesja zaczyna od czystego kontekstu

### Requirement: Instrukcje agenta pochodzą z obrazu

Instrukcje, skille, ustawienia uprawnień i konfiguracja serwerów MCP agenta MUST być przy każdym starcie kontenera
odtwarzane z obrazu. Zmiana tych plików w katalogu roboczym MUST NOT przetrwać restartu kontenera.

#### Scenario: Plik instrukcji zmieniony w kontenerze

- **WHEN** plik instrukcji w katalogu roboczym zostaje zmieniony, a kontener jest restartowany
- **THEN** sesja startuje z instrukcjami z obrazu

### Requirement: Telegram odpowiada tylko operatorowi

Agent MUST rozmawiać przez własnego bota Telegram, innego niż każdy bot zarejestrowany w pakiecie `/telegram`
workbencha. Agent MUST obsługiwać wyłącznie wiadomości z prywatnego czatu konta operatora wpisanego na allowliście;
wiadomości od innych kont i z grup MUST zostać zignorowane, a odpowiedź MUST NOT ujawniać niczego z systemu.
Odpowiedź dłuższa niż limit jednej wiadomości Telegram MUST dotrzeć w całości, w kolejnych wiadomościach.

#### Scenario: Wiadomość od obcego konta

- **WHEN** konto spoza allowlisty pisze do bota agenta
- **THEN** wiadomość nie trafia do sesji i agent nie odpowiada treścią z systemu

#### Scenario: Bot w grupie

- **WHEN** ktoś dodaje bota agenta do grupy i pisze w niej
- **THEN** wiadomości z grupy są ignorowane

#### Scenario: Bot agenta wpisany do `/telegram`

- **WHEN** porównywane są tokeny botów pakietu `/telegram` i bota agenta
- **THEN** token bota agenta nie występuje wśród nich

### Requirement: Sesja nie startuje przed narzędziami systemu

Po starcie serwera sesja MUST poczekać, aż workbench odpowie na publicznym adresie, zanim połączy serwery MCP — przez
ograniczony czas, po którym startuje i tak. Gdy kanał Telegram sesji przestał działać, MUST zostać połączony ponownie
bez restartu sesji.

#### Scenario: Restart całego serwera

- **WHEN** wszystkie kontenery startują jednocześnie, a workbench odpowiada po 40 sekundach
- **THEN** sesja startuje po odpowiedzi workbencha i ma jego narzędzia

#### Scenario: Kanał Telegram nie wstał

- **WHEN** sesja działa dłużej niż pół minuty, a proces kanału Telegram nie istnieje
- **THEN** w ciągu minuty kanał zostaje połączony ponownie

### Requirement: Agent pisze pierwszy o stałych porach, chyba że operator właśnie rozmawia

Agent MUST o porach z konfiguracji dostać do sesji polecenie przeglądu (rano przed otwarciem rynku europejskiego,
wieczorem podsumowanie) i odpowiedzieć nim w czacie operatora. Polecenie MUST zostać pominięte, gdy operator pisał do
agenta w ostatniej godzinie. Polecenie przypadające w czasie, gdy sesja nie działa, MUST zostać dostarczone po jej
powrocie, jeśli od pory minęła mniej niż godzina, a w przeciwnym razie pominięte. Pusta lista pór MUST wyłączać
przeglądy.

#### Scenario: Pora przeglądu bez rozmowy

- **WHEN** nadchodzi pora porannego przeglądu, a operator nie pisał od wczoraj
- **THEN** operator dostaje w Telegramie przegląd od agenta

#### Scenario: Operator właśnie rozmawia

- **WHEN** nadchodzi pora przeglądu, a operator pisał do agenta 20 minut wcześniej
- **THEN** przegląd jest pominięty

#### Scenario: Sesja w restarcie o porze przeglądu

- **WHEN** pora przeglądu przypada w czasie restartu sesji, a sesja wraca po 3 minutach
- **THEN** przegląd zostaje dostarczony po powrocie sesji, raz

### Requirement: Zdrowie agenta nie zależy od loginu

Kontener agenta MUST być zdrowy wtedy i tylko wtedy, gdy działa jego sesja i proces Claude Code w niej. Brak loginu
subskrypcji, brak parowania bota ani brak tokenu operatora MUST NOT czynić go niezdrowym, tak żeby wdrożenie reszty
systemu nie było wycofywane z powodu kroku, który operator wykonuje raz, ręcznie.

#### Scenario: Pierwsze wdrożenie przed loginem

- **WHEN** kontener agenta startuje po raz pierwszy, zanim operator zalogował subskrypcję
- **THEN** kontener jest zdrowy, a wdrożenie nie jest wycofywane
