# Design — the-screen-is-mostly-refusals

## Context

Motywacja w proposal.md. Stan zastany: platforma strategii działa na produkcji, terminal
nic o niej nie wie (zero trafień w `modules/terminal/src/`), a `polymarket-data` dostał
podstronę tej samej klasy tydzień temu — jest świeżym wzorcem i to z niego bierze się
kształt tej pracy.

Dwie rzeczy z tamtej roboty są tu wiążące. Klient modułu w terminalu żyje we własnym
katalogu, mapuje typy generowane z Pydantica na to, czego chcą widoki, i jest jedynym
miejscem, gdzie te dwa kształty się spotykają. A tożsamość jest **jedna na moduł**:
`config.scopes` trzyma po jednym zakresie na moduł, `identityFor(scope)` bierze token dla
tej publiczności, i moduł bez zakresu jest wołany bez poświadczenia.

## Goals / Non-Goals

**Goals:**

- Ekran, na którym odmowa jest czytelna razem ze swoim rodzajem — bo to jest zawartość.
- Droga do założenia pierwszej obserwacji; dziś nie ma żadnej.
- Typy generowane z modułu, żeby `contract:check` psuł się w dniu zmiany kontraktu.

**Non-Goals:**

- Uruchamianie backtestu z ekranu — to komenda i ma nią zostać.
- Wykresy nad decyzjami. Najpierw ma być co oglądać.
- Jakakolwiek akcja na rachunku. Moduł pod spodem nie ma do niego drogi.

## Decisions

**1. Delegowany zakres w rejestracji Easy Auth strategii, a nie dopisanie terminala do
cudzej publiczności.** Rejestracja tego modułu powstała dla wołających maszynowych i nie
ogłasza zakresu; przeglądarka nie ma więc o co poprosić. Rozważana alternatywa — pozwolić
terminalowi wysłać tu token wzięty dla market-daty, przez dopisanie tamtej publiczności do
`allowed_audiences` — jest wprost zakazana przez `terminal-identity` („token wzięty dla
jednego modułu MUST NOT być wysłany do drugiego") i byłaby cofnięciem reguły, którą ten
system zapłacił za ustalenie. Zakres kosztuje cztery linijki w module Terraforma.

**2. Ekran domyślnie pokazuje odmowy, a rodzaj odmowy jest kolumną, nie szczegółem.**
Odwrotność zwyczaju i sedno tej zmiany: przy strategii odrzucającej ponad 95% świec ekran
setupów jest pusty wtedy, gdy jest najbardziej potrzebny. Rodzaj wychodzi na wierzch, bo
„brak pokrycia" i „strategia powiedziała nie" mają różne lekarstwa, a zlanie ich w „brak
sygnału" wysyła operatora w złą stronę.

**3. Typy z generatora, nie pisane ręcznie.** Moduł dostaje `openapi.py` drukujący dokument
bez uruchamiania procesu — jak market-data, teams i polymarket-data — a terminal dokłada
źródło do `contract.mjs`. Ręczne DTO byłyby czwartą kopią kontraktu, która rozjeżdża się po
cichu; generowane psują `contract:check` w dniu zmiany. Kosztem jest wpisanie
`modules/strategy/` do filtra joba `terminal` w CI, bo inaczej ten sprawdzian nie pobiegnie
wtedy, kiedy jest potrzebny.

**4. Zakładanie obserwacji jest w zakresie, mimo że to zapis.** Kusiło, żeby pierwsza
podstrona tylko czytała. Ale platforma nie obserwuje dziś ani jednej pary i nie ma innej
drogi, którą pierwsza obserwacja mogłaby powstać — ekran wyłącznie czytający pokazywałby
pustkę bez sposobu, żeby ją zmienić. Zapisów jest dokładnie tyle, ile trzeba: założenie
obserwacji i przełącznik aktywności.

## Risks / Trade-offs

- [Ekran pełen odmów czyta się jak lista błędów] → rodzaj odmowy nazwany wprost i odmowa
  strategii wizualnie odróżniona od braku danych; „nie" strategii jest normalną pracą, nie
  usterką, i ekran ma to mówić.
- [Piąty zakres w konfiguracji terminala to piąte miejsce do pomylenia] → zakres modułu
  jest opcjonalny osobno, a jego brak daje wołanie bez poświadczenia i odmowę modułu —
  czytelną, nie cichą (`terminal-identity`).
- [`contract:check` zaczyna zależeć od trzeciego modułu] → to jest cel, nie koszt: filtr
  joba `terminal` już dziś obejmuje workbench i `market_data/contract.py` z tego samego
  powodu.

## Migration Plan

`terraform apply` przed wdrożeniem terminala, bo zakres delegowany musi istnieć, zanim
przeglądarka o niego poprosi. Kolejność jak zwykle: apply, potem deploy. Odwrót to
usunięcie zakładki — moduł działa dalej bez ekranu, tak jak działał do dziś.
