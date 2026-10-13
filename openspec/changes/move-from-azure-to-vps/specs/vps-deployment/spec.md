## Purpose

Jak system trafia na serwer i z niego wraca: serwer odtwarzalny z kodu, wdrożenie po zielonych testach
z sondą i powrotem, sekrety poza repozytorium, kopie bazy, które ktoś odtworzył.

## ADDED Requirements

### Requirement: Serwer jest odtwarzalny z repozytorium

Konfiguracja serwera MUST być w repozytorium i MUST dać się zastosować do świeżej maszyny dowolnego
dostawcy z obrazem Ubuntu LTS: logowanie wyłącznie kluczem SSH, bez logowania roota, zapora wpuszczająca
tylko porty proxy i SSH (SSH z ograniczonych adresów), automatyczne aktualizacje bezpieczeństwa,
Docker i rotacja logów kontenerów.

#### Scenario: Odtworzenie po utracie serwera

- **WHEN** operator stawia nową maszynę i stosuje konfigurację z repozytorium
- **THEN** serwer jest gotowy do wdrożenia bez ręcznych kroków poza podaniem adresu i kluczy

### Requirement: Wdrożenie po zielonych testach, z sondą i powrotem

Wdrożenie MUST startować tylko po zielonym przebiegu testów tego samego commita i MUST pomijać obrazy,
których commit nie zmienia. Po podmianie obrazów sonda MUST sprawdzić, że każdy podmieniony kontener
działa na obrazie z tego commita **i** odpowiada na trasie zdrowia. Gdy sonda zawodzi, wdrożenie MUST
samo przywrócić poprzednie obrazy, a przebieg MUST zakończyć się błędem.

#### Scenario: Obraz, który nie wstaje

- **WHEN** nowy obraz workbencha nie odpowiada na trasie zdrowia
- **THEN** wdrożenie przywraca poprzedni obraz i kończy się błędem
- **AND** po zakończeniu trasa zdrowia odpowiada

#### Scenario: Zmiana tylko w terminalu

- **WHEN** commit zmienia wyłącznie terminal
- **THEN** obrazy usług nie są podmieniane

### Requirement: Sekrety nie przechodzą przez repozytorium

Wartości sekretów MUST pochodzić z magazynu sekretów CI i MUST trafiać na serwer do pliku czytelnego
tylko dla użytkownika aplikacji. Repozytorium MUST zawierać listę wymaganych nazw; wdrożenie MUST
odmówić, gdy którejś wartości brakuje, zanim podmieni jakikolwiek obraz. Wartości MUST NOT pojawiać
się w logach wdrożenia ani w argumentach poleceń.

#### Scenario: Brakujący sekret

- **WHEN** w magazynie CI brakuje wartości z listy wymaganych
- **THEN** wdrożenie kończy się błędem nazywającym brakującą nazwę
- **AND** działające kontenery zostają nietknięte

### Requirement: Kopie bazy są codzienne, poza serwerem i odtwarzane

Każda baza systemu MUST mieć codzienny zrzut przechowywany poza serwerem, z retencją co najmniej 14 dni.
Brak zrzutu z ostatniej doby MUST wywołać alert do operatora. Odtworzenie zrzutu na świeżej maszynie
MUST być przećwiczone przed przełączeniem produkcji i powtarzane co miesiąc.

#### Scenario: Nocna kopia się nie udała

- **WHEN** zrzut którejkolwiek bazy nie powstał w ostatniej dobie
- **THEN** operator dostaje alert nazywający bazę

#### Scenario: Próba odtworzenia

- **WHEN** zrzuty są odtwarzane na świeżej maszynie
- **THEN** wszystkie moduły startują na odtworzonych danych, a liczby wierszy zgadzają się ze źródłem
