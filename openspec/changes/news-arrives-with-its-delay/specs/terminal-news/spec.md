## Purpose

Zakładka terminala z newsami: co operator widzi po jej otwarciu, jak podane jest opóźnienie każdego
newsa i każdego źródła, oraz co ekran mówi, gdy źródło stoi albo odmawia.

## ADDED Requirements

### Requirement: Zakładka pokazuje newsy z nazwanego okna

Zakładka MUST pokazywać newsy z wybranego okna. Operator MUST móc wybrać okno spośród: 5 minut,
15 minut, 1 godziny, 4 godzin, 24 godzin i 7 dni; domyślnym oknem jest 4 godziny. Zakładka MUST nazywać
okno i liczbę newsów wprost, a gdy kontrakt obciął listę, MUST to powiedzieć. Operator MUST móc zawęzić
listę do wybranych źródeł i do tekstu.

#### Scenario: Otwarcie zakładki

- **WHEN** operator otwiera zakładkę
- **THEN** widzi newsy z ostatnich 4 godzin wraz z liczbą i nazwą okna

#### Scenario: Zmiana okna

- **WHEN** operator wybiera okno 7 dni
- **THEN** zakładka MUST zapytać o siedem dni i nazwać okno w nagłówku

#### Scenario: Lista obcięta

- **WHEN** kontrakt odpowiada, że lista jest obcięta
- **THEN** ekran MUST to powiedzieć, zamiast udawać, że pokazuje całe okno

### Requirement: Kliknięcie otwiera cały news w aplikacji

Kliknięcie w news MUST rozwijać go w miejscu i pokazywać całą treść, jaką archiwum ma: treść, gdy
feed ją niósł, a w przeciwnym razie lead, z zachowanymi akapitami. Kliknięcie MUST NOT przenosić operatora
na stronę źródła. Adres oryginału MUST być dostępny jako osobny, jawny odnośnik w rozwiniętej części. Gdy
archiwum ma sam lead, ekran MUST to powiedzieć, zamiast udawać, że pokazuje cały artykuł. Przycisk
zachowania MUST działać niezależnie od rozwijania.

#### Scenario: Rozwinięcie newsa z treścią

- **WHEN** operator klika news, który feed niósł z treścią w kilku akapitach
- **THEN** karta MUST pokazać całą treść w aplikacji, z akapitami
- **AND** tytuł MUST NOT być odnośnikiem do strony źródła

#### Scenario: News z samym leadem

- **WHEN** operator rozwija news, którego feed niósł tylko z leadem
- **THEN** karta MUST pokazać ten lead w całości i powiedzieć, że pełny tekst jest u źródła

#### Scenario: Zachowanie nie rozwija

- **WHEN** operator klika przycisk zachowania na zwiniętej karcie
- **THEN** karta MUST pozostać zwinięta

### Requirement: Newsy dają się sortować po czasie

Operator MUST móc uporządkować listę po czasie publikacji, po momencie pierwszego zobaczenia i po
czasie oczekiwania (górna granica opóźnienia), w obu kierunkach. News bez zmierzonego opóźnienia MUST
stać na końcu przy sortowaniu po oczekiwaniu, w obu kierunkach. News bez czasu publikacji MUST być
umieszczony według momentu pierwszego zobaczenia. Domyślny porządek to publikacja od najnowszej.

#### Scenario: Sortowanie po oczekiwaniu

- **WHEN** operator wybiera sortowanie po oczekiwaniu od najdłuższego
- **THEN** news, który czekał najdłużej, MUST być pierwszy, a news bez pomiaru ostatni

#### Scenario: Odwrócenie kierunku

- **WHEN** operator odwraca kierunek sortowania
- **THEN** lista MUST wystąpić w odwrotnym porządku, z newsami bez pomiaru nadal na końcu

### Requirement: Źródła wybiera się jednym kliknięciem

Zakładka MUST domyślnie mieć zaznaczone wszystkie źródła. Operator MUST móc jednym kliknięciem zaznaczyć
wszystkie, odznaczyć wszystkie i zostawić tylko źródła, które odpowiadają. Źródło, które pojawi się
w zestawieniu później, MUST być zaznaczone. Gdy nie wybrano żadnego źródła, ekran MUST to powiedzieć
i MUST NOT pytać kontraktu, bo pusta lista źródeł oznacza tam „wszystkie”.

#### Scenario: Wszystkie i żadne

- **WHEN** operator klika „Żadne”, a potem „Wszystkie”
- **THEN** po pierwszym kliknięciu ekran MUST powiedzieć, że nie wybrano źródła, a po drugim MUST znów pokazać newsy ze wszystkich

#### Scenario: Tylko działające

- **WHEN** operator klika „Tylko działające”, a jedno źródło odmawia
- **THEN** źródło odmawiające MUST być odznaczone, a pozostałe zaznaczone

### Requirement: News pokazuje swoje opóźnienie

Karta newsa MUST pokazywać tytuł i lead w języku źródła, wydawcę, czas publikacji, opóźnienie
i — po rozwinięciu — drogę do oryginału. Opóźnienie MUST być pokazane jako zakres od granicy dolnej do górnej. Gdy go
nie ma, karta MUST pokazać powód, na przykład „zastany” albo „brak czasu publikacji”. MUST NOT
pokazywać zera ani pustego miejsca bez wyjaśnienia.

#### Scenario: News ze zmierzonym opóźnieniem

- **WHEN** news ma granicę dolną 3 minuty i górną 5 minut
- **THEN** karta MUST pokazać oba końce zakresu

#### Scenario: News bez czasu publikacji

- **WHEN** feed nie podał czasu publikacji
- **THEN** karta MUST pokazać, że opóźnienia nie da się zmierzyć i dlaczego

### Requirement: Operator zachowuje news jednym przyciskiem

Karta newsa MUST mieć przycisk, który stawia albo zdejmuje znacznik zachowania, i MUST pokazywać,
czy news jest zachowany. Dla niezachowanego MUST pokazywać, kiedy zniknie. Zakładka MUST dawać widok
samych newsów zachowanych. Nieudana zmiana znacznika MUST zostawić kartę w stanie sprzed kliknięcia
i MUST powiedzieć, że się nie udało.

#### Scenario: Zachowanie newsa

- **WHEN** operator klika przycisk zachowania na karcie
- **THEN** karta MUST pokazać news jako zachowany, bez momentu zniknięcia

#### Scenario: Zdjęcie znacznika ze starego newsa

- **WHEN** operator zdejmuje znacznik z newsa starszego niż okres retencji
- **THEN** ekran MUST powiedzieć, że news zniknie przy najbliższym czyszczeniu

#### Scenario: Zmiana znacznika się nie udała

- **WHEN** kontrakt odmawia albo nie odpowiada na zmianę znacznika
- **THEN** karta MUST wrócić do poprzedniego stanu i MUST pokazać błąd

### Requirement: Zestawienie źródeł odpowiada, komu ufać

Zakładka MUST pokazywać zestawienie wszystkich źródeł. Przy każdym MUST być:

- stan,
- moment ostatniego udanego pobrania,
- mediana i 90. percentyl opóźnienia z doby,
- wiek najnowszego newsa,
- liczba newsów.

Źródło stojące, odmawiające albo z nieczytelnym feedem MUST być wyróżnione, wraz z powodem
i momentem ostatniego udanego pobrania.

#### Scenario: Jedno źródło odmawia

- **WHEN** jedno ze źródeł od godziny odpowiada odmową
- **THEN** zestawienie MUST je wyróżnić z powodem i momentem ostatniego udanego pobrania
- **AND** newsy pozostałych źródeł MUST być pokazywane normalnie

### Requirement: Pusta lista mówi, dlaczego jest pusta

Zakładka MUST odróżniać brak newsów w oknie przy działających źródłach od sytuacji, w której
żadne źródło nie ma świeżego udanego pobrania. MUST NOT odpowiadać na obie tą samą pustą listą.

#### Scenario: Wszystkie źródła stoją

- **WHEN** żadne źródło nie ma udanego pobrania z ostatnich kilku odstępów
- **THEN** ekran MUST powiedzieć, że zbiór stoi, zamiast pokazywać pustą listę

### Requirement: Lista odświeża się sama i nie gubi tego, co pokazuje

Zakładka MUST odświeżać newsy i stan źródeł bez czynności operatora. Nieudane odświeżenie MUST NOT
skasować tego, co jest już na ekranie.

#### Scenario: Odświeżenie nie dochodzi

- **WHEN** odświeżenie kończy się błędem, a lista jest już wypełniona
- **THEN** poprzednie newsy MUST zostać na ekranie
