## Purpose

Co platforma gwarantuje o własnej telemetrii po stronie odbiorcy: że jeden dzień logów ma
ograniczony koszt, że osiągnięcie tej granicy jest zdarzeniem, o którym operator się dowiaduje,
i że miesięczny rachunek ma próg, po którym przychodzi list — zanim przyjdzie faktura.

## ADDED Requirements

### Requirement: Dzień logów ma sufit

Workspace telemetrii MUST przyjmować w ciągu doby najwyżej ustaloną ilość danych; dane ponad
tę ilość MUST być odrzucane do najbliższego resetu dobowego, a nie przyjmowane i liczone.
Sufit MUST stać z co najmniej dziesięciokrotnym zapasem nad dobowym ingestem zdrowego systemu,
tak by zwykły dzień — łącznie z dniem wdrożenia, kiedy każdy proces startuje od nowa — nigdy
go nie dotykał.

#### Scenario: Zwykły dzień

- **WHEN** osiem aplikacji pracuje normalnie i wysyła dobowy wolumen telemetrii zdrowego
  systemu
- **THEN** nic nie jest odrzucone, a operator niczego nie zauważa

#### Scenario: Pętla taka jak sierpniowa

- **WHEN** jeden moduł zaczyna wysyłać po jednym rekordzie na każdą ramkę strumienia,
  wielokrotność normalnego wolumenu
- **THEN** zbieranie staje po osiągnięciu sufitu i wznawia się przy resecie
- **AND** koszt tego dnia nie przekracza ceny sufitu, niezależnie od tego, jak długo pętla
  trwa

### Requirement: Osiągnięcie sufitu budzi operatora

Zatrzymane zbieranie wygląda z zewnątrz jak spokój: alerty, które czytają telemetrię, milkną
razem z nią. Platforma MUST powiadomić operatora, że sufit został osiągnięty, tym samym kanałem,
którym idą pozostałe alerty, i MUST zrobić to w ciągu godziny od zdarzenia. Powiadomienie MUST
NOT być wysyłane, gdy sufit nie został osiągnięty.

#### Scenario: Sufit osiągnięty w środku dnia

- **WHEN** dobowy wolumen dochodzi do sufitu o dowolnej porze
- **THEN** operator dostaje powiadomienie w ciągu godziny, zanim minie reset
- **AND** powiadomienie mówi, że zbieranie stoi, a nie że coś jest nie tak z modułem

#### Scenario: Sufit nieosiągnięty

- **WHEN** doba kończy się poniżej sufitu
- **THEN** żadne powiadomienie o suficie nie wychodzi

### Requirement: Miesięczny rachunek ma budżet z ostrzeżeniem

Subskrypcja MUST mieć miesięczny budżet, a operator MUST dostać powiadomienie, gdy
prognozowany koszt miesiąca przekroczy ustaloną część budżetu i osobno, gdy koszt
rzeczywisty przekroczy budżet w całości. Budżet MUST NOT niczego zatrzymywać — jest
powiadomieniem, nie ogranicznikiem — a jego kwota MUST leżeć nad tempem zdrowego systemu
na tyle, by miesiąc bez incydentu nie budził nikogo.

#### Scenario: Miesiąc jak zwykle

- **WHEN** koszt miesiąca układa się w tempie zdrowego systemu
- **THEN** żadne powiadomienie budżetowe nie wychodzi

#### Scenario: Prognoza przekracza próg

- **WHEN** prognoza kosztu na koniec miesiąca przekracza ustaloną część budżetu
- **THEN** operator dostaje powiadomienie z kwotą i prognozą, zanim miesiąc się skończy

#### Scenario: Budżet przekroczony

- **WHEN** koszt rzeczywisty miesiąca przekracza budżet
- **THEN** operator dostaje osobne powiadomienie
- **AND** żadna usługa nie zostaje zatrzymana ani ograniczona z tego powodu
