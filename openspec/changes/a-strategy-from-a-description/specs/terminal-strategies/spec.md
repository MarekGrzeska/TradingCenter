## Purpose

Zakładka Strategies w terminalu. Operator czyta tu to, co napisał agent, poprawia to ręcznie, uruchamia backtest i czyta
raport, bez wysyłania JSON-a pod REST.

## ADDED Requirements

### Requirement: Zakładka pokazuje strategie albo mówi, dlaczego nie może

Zakładka MUST wymieniać strategie z nazwą, instrumentem, interwałem decyzji (w nazwach terminala), ostatnią rewizją z jej
autorem i licznikiem prób, a osobno strategie zarchiwizowane. Zakładka MUST pozwalać strategię zarchiwizować i
przywrócić. Gdy pakiet strategii nie jest częścią procesu, zakładka MUST to powiedzieć i nazwać `STRATEGIES_DATABASE_URL`
zamiast pokazywać pustą listę.

#### Scenario: Pakiet nieobecny

- **WHEN** workbench działa bez bazy strategii
- **THEN** zakładka MUST mówić, że pakiet strategii nie jest włączony, i nazywać ustawienie, które go włącza

### Requirement: Edytor z podpowiedziami i walidacją na żywo

Edytor MUST pokazywać tekst dokumentu otwartej strategii. Podpowiedzi MUST pochodzić z `GET /language` i z samego
dokumentu: sekcje, funkcje z sygnaturami, wskaźniki katalogu, nazwy z `let`, parametry `p.*` oraz, po `@`, interwały i
instrumenty, które archiwum zbiera. Terminal MUST NOT nieść własnej listy funkcji języka.

Błąd składni JSON MUST być zaznaczony od razu. Problemy z `POST /validate` MUST pojawiać się po przerwie w pisaniu, każdy
w swoim miejscu (ścieżka i kolumna formuły) i ze swoją podpowiedzią. Walidacja MUST NOT być wysyłana dla tekstu, który się
nie zmienił, ani wtedy, gdy zakładka nie jest na ekranie.

Zapis MUST być możliwy tylko dla dokumentu bez problemów, MUST zapisywać autora `operator` i MUST wskazywać rewizję, na
której edycja się opiera. Gdy w międzyczasie powstała nowsza rewizja, zakładka MUST pokazać odmowę i dać wybór między
wczytaniem nowszej rewizji (z porzuceniem zmian) a dalszą edycją. MUST NOT nadpisywać nowszej rewizji bez tego wyboru.

#### Scenario: Literówka w nazwie funkcji

- **WHEN** operator wpisuje `emaa(20)` w warunku wejścia
- **THEN** po przerwie w pisaniu edytor MUST zaznaczyć `emaa` w tej formule i pokazać podpowiedź `ema`

#### Scenario: Zapis, gdy agent zapisał w międzyczasie

- **WHEN** operator zapisuje edycję opartą na rewizji 4, a agent zapisał już rewizję 5
- **THEN** zakładka MUST pokazać, że istnieje rewizja 5, i MUST NOT zapisać rewizji 6 bez decyzji operatora

### Requirement: Streszczenie obok edytora

Obok edytora MUST stać streszczenie dokumentu z ostatniej walidacji, a w nim osobno `hypothesis` i `notes` jako założenia
autora. Gdy tekst ma problemy, zakładka MUST mówić, że streszczenie nie opisuje bieżącego tekstu. MUST NOT pokazywać
streszczenia poprzedniej poprawnej wersji tak, jakby było aktualne.

#### Scenario: Zmiana stopu w edytorze

- **WHEN** operator zmienia `exits.stop` z `2 * at_entry(atr(14))` na `1.5 * at_entry(atr(14))`
- **THEN** po walidacji streszczenie MUST mówić o stopie 1,5 ATR

#### Scenario: Tekst z błędem

- **WHEN** tekst w edytorze ma problem
- **THEN** zakładka MUST mówić, że streszczenie czeka na poprawny dokument

### Requirement: Historia rewizji z różnicami

Zakładka MUST wymieniać rewizje otwartej strategii od najnowszej, z numerem, autorem i czasem. Wybrana rewizja MUST
pokazywać zmiany względem poprzedniej po ścieżkach dokumentu, z wartością przed i po. Starszą rewizję MUST dać się
przywrócić: jej treść zostaje zapisana jako kolejna rewizja, a żadna istniejąca się nie zmienia.

#### Scenario: Rewizja agenta

- **WHEN** operator wybiera rewizję 5 zapisaną przez agenta
- **THEN** zakładka MUST pokazywać autora `agent` i zmienione ścieżki z wartościami przed i po

#### Scenario: Przywrócenie rewizji

- **WHEN** operator przywraca rewizję 3 strategii, której ostatnią rewizją jest 5
- **THEN** MUST powstać rewizja 6 o treści rewizji 3
- **AND** rewizje 3, 4 i 5 MUST pozostać bez zmian

### Requirement: Zakładka współpracuje z panelem agenta

Gdy zakładka jest na ekranie z otwartą strategią, każda tura wysłana z panelu agenta MUST nieść identyfikator strategii,
rewizję, na której opiera się edytor, oraz tekst edytora, jeśli różni się od tej rewizji. Po każdej zakończonej turze
zakładka MUST na nowo przeczytać listę strategii, otwartą strategię i jej uruchomienia.

Gdy agent zapisał nową rewizję otwartej strategii, a operator nie ma niezapisanych zmian, edytor MUST ją wczytać i
zakładka MUST powiedzieć, że zapisał ją agent. Gdy operator ma niezapisane zmiany, edytor MUST NOT ich nadpisać i MUST
powiedzieć, że istnieje nowsza rewizja. Strategia utworzona przez agenta w turze, w której zakładka nie miała otwartej
strategii, MUST zostać otwarta.

#### Scenario: Agent poprawia otwartą strategię

- **WHEN** operator prosi w panelu „zmień stop na 1,5 ATR” z otwartą strategią bez niezapisanych zmian
- **THEN** po turze edytor MUST pokazywać nową rewizję, a zakładka MUST mówić, że zapisał ją agent

#### Scenario: Niezapisane zmiany operatora

- **WHEN** agent zapisuje nową rewizję, a w edytorze są niezapisane zmiany operatora
- **THEN** edytor MUST zachować zmiany operatora i MUST mówić, że istnieje nowsza rewizja

#### Scenario: Nowa strategia z opisu

- **WHEN** operator bez otwartej strategii opisuje strategię w panelu, a agent ją zapisuje
- **THEN** po turze zakładka MUST otworzyć tę strategię

### Requirement: Uruchomienie z formularza i profil kosztów

Formularz uruchomienia MUST przyjmować zakres w dniach strefy polskiej, parametry z wartościami domyślnymi i
zadeklarowanymi zakresami, model kosztów, kapitał i ziarno. Model kosztów MUST być wypełniony z profilu kosztów
instrumentu. Zmiana w formularzu MUST dotyczyć tylko tego uruchomienia, a profil zmienia się osobno. Przed wysłaniem
formularz MUST pokazywać, ile minut obejmie zakres, wobec sufitu pakietu. Instrument bez profilu MUST dawać formularz z
pustymi kosztami i możliwością zapisania ich jako profil. Odmowa pakietu MUST pojawić się przy polu, którego dotyczy.

#### Scenario: Zakres ponad sufit

- **WHEN** operator wybiera zakres, który obejmuje więcej minut, niż pakiet przyjmuje
- **THEN** formularz MUST to powiedzieć przed wysłaniem i nazwać sufit

#### Scenario: Instrument bez profilu kosztów

- **WHEN** operator otwiera formularz dla instrumentu bez profilu
- **THEN** koszty MUST być puste, a formularz MUST pozwalać zapisać wpisane koszty jako profil instrumentu

### Requirement: Lista uruchomień i ich stan

Zakładka MUST wymieniać uruchomienia otwartej strategii ze wszystkich rewizji, od najnowszego. Każde MUST pokazywać stan,
rewizję, zakres, zlecającego (operator albo agent) i główne metryki. Nieudane MUST pokazywać przyczynę. Dopóki
któreś uruchomienie czeka albo się liczy, zakładka MUST odświeżać ich stan, a gdy żadne nie czeka, MUST przestać.
Uruchomienie czekające albo liczone MUST dać się anulować.

#### Scenario: Uruchomienie się kończy

- **WHEN** liczone uruchomienie się kończy, gdy zakładka jest otwarta
- **THEN** jego stan i główne metryki MUST pojawić się bez przeładowania strony

### Requirement: Raport z krzywą kapitału i transakcjami na wykresie

Raport MUST pokazywać:
- wszystkie metryki z `strategies-reports`, a metrykę pustą jako brak wartości, nigdy jako zero;
- punkty odniesienia;
- koszty według składników;
- liczbę rozstrzygnięć pesymistycznych;
- pochodzenie wyniku: rewizję i hash, wersję silnika, ziarno, zakres i koszty;
- dzienną krzywą kapitału z obsunięciem.

Transakcje MUST być listą stronicowaną z przyczyną wyjścia i oznaczeniem rozstrzygnięcia pesymistycznego. Obok MUST stać
wykres ceny instrumentu na interwale strategii ze znacznikami wejść i wyjść transakcji z bieżącej strony. Wybór
transakcji MUST przesuwać wykres do niej i rysować jej wejście, wyjście i początkowy stop. Zakładka MUST NOT pokazywać
oceny strategii.

#### Scenario: Wybór transakcji

- **WHEN** operator wybiera transakcję z listy
- **THEN** wykres MUST pokazać fragment osi z tą transakcją i jej wejście, wyjście oraz początkowy stop

#### Scenario: Raport bez transakcji

- **WHEN** uruchomienie nie otworzyło żadnej pozycji
- **THEN** raport MUST mówić, że transakcji nie było, a metryki zależne od transakcji MUST być pokazane jako brak wartości

#### Scenario: Uruchomienie sprzed krzywej kapitału

- **WHEN** raport pochodzi z wersji silnika, która nie zapisywała krzywej
- **THEN** zakładka MUST mówić, że to uruchomienie nie ma krzywej, zamiast rysować pusty wykres
