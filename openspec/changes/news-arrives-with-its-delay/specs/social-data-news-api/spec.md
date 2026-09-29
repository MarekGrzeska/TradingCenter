## Purpose

Trasy kontraktu, przez które terminal i pocket czytają newsy i stan źródeł: okno, zawężenia,
porządek i obcięcie, oraz jedyna trasa zapisująca w `/social`: znacznik zachowania newsa.

## ADDED Requirements

### Requirement: Newsy czyta się oknem, z jawnymi zawężeniami

Kontrakt MUST pozwalać pytać o newsy oknem czasu: skrótem „ostatnie N godzin” albo parą od–do.
Wynik MUST dać się zawęzić do jednego lub kilku źródeł oraz do tekstu, który występuje w tytule
albo leadzie, bez względu na wielkość liter. Okno, którego koniec jest wcześniejszy niż początek,
MUST być odmówione z powodem nazywającym błąd.

#### Scenario: Newsy o Iranie z dwóch źródeł

- **WHEN** klient prosi o newsy z ostatnich 6 godzin z dwóch źródeł, zawierające „iran”
- **THEN** odpowiedź MUST zawierać wyłącznie newsy spełniające wszystkie trzy warunki, także te z „Iran” w leadzie

#### Scenario: Okno bez sensu

- **WHEN** klient podaje okno, którego koniec jest wcześniejszy niż początek
- **THEN** kontrakt MUST odmówić z powodem, a nie zwrócić pustą listę

### Requirement: Porządek i obcięcie są jawne

Kontrakt MUST zwracać newsy od najnowszego według czasu publikacji, a news bez niego według
momentu pierwszego zobaczenia. Liczba newsów w odpowiedzi MUST mieć górną granicę. Gdy okno
zawiera więcej newsów, niż odpowiedź niesie, odpowiedź MUST to powiedzieć.

#### Scenario: Okno większe niż limit

- **WHEN** w oknie jest więcej newsów, niż wynosi limit odpowiedzi
- **THEN** odpowiedź MUST nieść najnowsze newsy i znacznik, że lista jest obcięta

### Requirement: Pola czasu i opóźnienia są zawsze obecne

Każdy news w odpowiedzi MUST nieść identyfikator źródła, wydawcę, tytuł, lead, adres oryginału,
trzy momenty, obie granice opóźnienia, powód braku opóźnienia, znacznik zachowania i moment, po
którym news zniknie. Ten ostatni jest pusty dla newsa zachowanego. Brak wartości MUST być wartością
pustą, a nie brakiem pola.

#### Scenario: News bez czasu publikacji

- **WHEN** klient odczytuje news, któremu feed nie podał czasu publikacji
- **THEN** pola czasu publikacji i obu granic MUST być obecne i puste, a powód MUST być podany

### Requirement: Znacznik zachowania stawia się i zdejmuje przy jednym newsie

Kontrakt MUST publikować trasę, która przy newsie wskazanym parą źródło–identyfikator stawia albo
zdejmuje znacznik zachowania i zwraca news w stanie po zmianie. Postawienie znacznika już stojącego
i zdjęcie nieobecnego MUST być bez skutku i bez błędu. News, którego nie ma, MUST być odmówiony
z powodem, a nie utworzony.

Kontrakt MUST też pozwalać odczytać same newsy zachowane, bez względu na okno.

#### Scenario: Operator zachowuje news

- **WHEN** klient stawia znacznik zachowania przy istniejącym newsie
- **THEN** odpowiedź MUST nieść ten news ze znacznikiem i z pustym momentem zniknięcia

#### Scenario: News, którego nie ma

- **WHEN** klient stawia znacznik przy parze źródło–identyfikator, której nie ma w archiwum
- **THEN** kontrakt MUST odmówić z powodem

#### Scenario: Lista zachowanych

- **WHEN** klient prosi o newsy zachowane
- **THEN** odpowiedź MUST zawierać każdy zachowany news, także starszy niż jakiekolwiek okno

### Requirement: Stan źródeł wymienia każde zadeklarowane źródło

Kontrakt MUST publikować trasę stanu źródeł newsów, na której każde zadeklarowane źródło występuje
ze swoim rachunkiem opóźnień (`social-data-news-latency`). Dotyczy to także źródła, które jeszcze
nigdy nie zostało pobrane albo nigdy nie odpowiedziało.

#### Scenario: Źródło, które nigdy nie odpowiedziało

- **WHEN** zadeklarowane źródło od startu procesu przy każdym pobraniu odmawia
- **THEN** trasa stanu MUST je wymienić, z pustym momentem udanego pobrania i powodem ostatniej porażki
