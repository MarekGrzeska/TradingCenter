## ADDED Requirements

### Requirement: Decyzja platformy strategii jest źródłem warunku

Moduł MUST dać się skonfigurować z serwerem narzędzi platformy strategii na tych samych
warunkach, co z każdym innym serwerem narzędzi (`teams-tool-access`, „Tryb połączenia z serwerem
narzędzi jest wybrany jednoznacznie"): brak adresu jest stanem wspieranym, adres zdalny bez
tożsamości odmową startu. Liczba oczekujących setupów, którą ta platforma publikuje, MUST być
czytana przez wyzwalacz tą samą drogą, co każda inna wielkość — po nazwie narzędzia i ścieżce
pola — i MUST NOT wymagać osobnego rodzaju wyzwalacza ani osobnego klienta.

Rdzeń decyduje, zespół się spiera — to jest szew, dla którego platforma strategii powstała, a
bez adresu po tej stronie jej decyzja dociera wyłącznie na telefon operatora. Osobny klient
byłby drugą drogą do tej samej liczby, a „Warunek jest czytany narzędziami serwera narzędzi"
drugiej drogi zabrania: wyzwalacz reagujący na inną wartość niż ta, którą zobaczy zespół, jest
gorszy niż brak wyzwalacza.

#### Scenario: Setup znaleziony przez rdzeń budzi zespół

- **WHEN** platforma strategii zapisuje decyzję o wejściu, a wyzwalacz porównuje liczbę
  oczekujących setupów tej strategii z progiem
- **THEN** przy najbliższym sprawdzeniu rusza dokładnie jeden przebieg
- **AND** żadne sprawdzenie przed nim nie kosztowało tokenów modelu

#### Scenario: Moduł bez adresu platformy strategii

- **WHEN** operator zapisuje wyzwalacz nazywający narzędzie platformy strategii, a moduł nie ma
  jej adresu
- **THEN** zapis zostaje odrzucony z powodem nazywającym brak serwera, który ogłasza tę nazwę
