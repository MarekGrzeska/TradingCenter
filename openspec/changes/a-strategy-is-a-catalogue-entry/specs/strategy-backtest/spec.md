## Purpose

Weryfikacja strategii na historii: jedno odtwarzanie i jeden model kosztów dla każdego
wpisu katalogu, z wynikiem, który da się odtworzyć i uczciwie porównać między strategiami.

## ADDED Requirements

### Requirement: Backtest woła tę samą funkcję oceny co pętla

Backtest MUST wyliczać decyzje tą samą funkcją oceny, którą woła pętla na żywo — druga
implementacja reguł strategii MUST NOT istnieć. Przebieg podający historię przyrostowo,
świeca po świecy, MUST dawać decyzje identyczne z przebiegiem wsadowym po całym zakresie.

Test przyrostowe-równa-się-wsadowe jest jedynym testem, który wykrywa podglądanie
przyszłości; żeby miał czego się trzymać, musi istnieć dokładnie jedna funkcja do porównania
samej ze sobą.

#### Scenario: Przebieg przyrostowy i wsadowy

- **WHEN** ten sam zakres historii przechodzi przez backtest świeca po świecy i wsadowo
- **THEN** oba przebiegi produkują identyczne decyzje

### Requirement: Przedłużenie historii nie zmienia wcześniejszych decyzji

Decyzja backtestu dla świecy MUST zależeć wyłącznie od danych do tej świecy włącznie.
Powtórzenie backtestu na zakresie przedłużonym w przód MUST dawać dla wspólnej części
dokładnie te same decyzje.

To jest zakaz repaintu podniesiony na poziom strategii: krzywa kapitału, która poprawia się
od doczytania przyszłości, jest artefaktem pomiaru, nie przewagą.

#### Scenario: Ten sam początek, dłuższy koniec

- **WHEN** backtest biegnie po zakresie, a następnie po zakresie przedłużonym o kolejne świece
- **THEN** decyzje we wspólnej części obu przebiegów są identyczne

### Requirement: Wynik nazywa swoje koszty i swoje parametry

Raport backtestu MUST nazywać model kosztów (spread, prowizję, poślizg), wersję zestawu
parametrów strategii i zakres danych, na którym powstał. Wynik bez modelu kosztów MUST NOT
być prezentowany jako wynik strategii. Powtórzenie backtestu z tych samych składników MUST
dawać ten sam raport.

Archiwum trzyma stronę bid — koszt transakcyjny jest w danych niewidoczny, a strategia
o wysokim stosunku zysku do ryzyka potrafi stracić całą przewagę na spreadzie. Raport,
który nie mówi, co założył, mówi tylko tyle, że ktoś go wygenerował.

#### Scenario: Raport z przebiegu

- **WHEN** backtest kończy przebieg
- **THEN** raport niesie model kosztów, wersję parametrów i zakres danych
- **AND** ponowny przebieg z tych samych składników daje ten sam raport

### Requirement: Strategie porównuje się na tych samych danych i kosztach

Porównanie strategii MUST zestawiać przebiegi wykonane na tym samym zakresie danych i tym
samym modelu kosztów; raport porównawczy MUST odmówić zestawienia przebiegów, których
składniki się różnią, nazywając różnicę.

Po to istnieje strategia odniesienia: „strategia działa" nie znaczy nic, dopóki nie znaczy
„bije prosty punkt odniesienia o tyle, po kosztach". Porównanie na różnych danych to
porównanie pogody w dwóch miastach.

#### Scenario: Zestawienie dwóch strategii

- **WHEN** operator zestawia przebiegi dwóch strategii na tym samym zakresie i modelu kosztów
- **THEN** raport porównawczy staje obok siebie na wspólnych metrykach

#### Scenario: Zestawienie przebiegów o różnych składnikach

- **WHEN** operator zestawia przebiegi wykonane na różnych zakresach lub kosztach
- **THEN** zestawienie zostaje odrzucone z powodem nazywającym różnicę

### Requirement: Backtest niczego nie zmienia poza własnym zapisem wyników

Przebieg backtestu MUST NOT zmieniać stanu żadnego innego modułu ani stanu strategii na
żywo: nie składa zleceń, nie pisze do archiwum, nie dotyka zapisu decyzji pętli. Jedynym
śladem przebiegu MUST być jego własny raport.

#### Scenario: Przebieg backtestu a reszta systemu

- **WHEN** backtest wykonuje przebieg po historii
- **THEN** żaden inny moduł nie odnotowuje zapisu
- **AND** zapis decyzji pętli na żywo pozostaje nietknięty
