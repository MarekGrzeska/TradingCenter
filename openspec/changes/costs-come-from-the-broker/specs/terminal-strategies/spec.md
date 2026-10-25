## MODIFIED Requirements

### Requirement: Uruchomienie z formularza i profil kosztów

Formularz uruchomienia MUST przyjmować zakres w dniach strefy polskiej, parametry z wartościami domyślnymi i
zadeklarowanymi zakresami, model kosztów, kapitał i ziarno. Model kosztów MUST być wypełniony z profilu kosztów
instrumentu. Instrument bez profilu MUST dostać profil pobrany od brokera, bez kroku operatora, a formularz MUST
pokazywać źródło kosztów i chwilę ich pobrania. Zmiana w formularzu MUST dotyczyć tylko tego uruchomienia. Profil
zmienia się osobno, w tym przez pobranie go od brokera od nowa. Formularz MUST mieć wybór „bez kosztów”, który wysyła
uruchomienie bez kosztów i mówi, że jego wynik będzie nierealistyczny. Przed wysłaniem formularz MUST pokazywać, ile
minut obejmie zakres, wobec sufitu pakietu. Odmowa pakietu MUST pojawić się przy polu, którego dotyczy.

#### Scenario: Zakres ponad sufit

- **WHEN** operator wybiera zakres, który obejmuje więcej minut, niż pakiet przyjmuje
- **THEN** formularz MUST to powiedzieć przed wysłaniem i nazwać sufit

#### Scenario: Instrument bez profilu kosztów

- **WHEN** operator otwiera formularz dla instrumentu bez profilu
- **THEN** koszty MUST zostać pobrane od brokera i pokazane ze źródłem „capital.com” i chwilą pobrania
- **AND** operator MUST NOT musieć niczego wpisywać, żeby uruchomić backtest

#### Scenario: Backtest bez kosztów

- **WHEN** operator wybiera „bez kosztów” i uruchamia backtest
- **THEN** uruchomienie MUST być wysłane bez kosztów, a jego raport i pozycja na liście MUST być tak oznaczone

## ADDED Requirements

### Requirement: Okno tworzenia strategii ma własny czat z agentem

Obok edytora otwartej strategii MUST stać czat z agentem, osobny od panelu agenta terminala i widoczny bez rozwijania
czegokolwiek, tak jak pole „opisz zdaniem” w zakładce Alerty. Każda strategia MUST mieć swoją rozmowę: otwarcie
strategii MUST wczytać jej rozmowę, a nowa strategia MUST zaczynać od pustej. Rozmowa utworzona przy nowej strategii MUST
zostać przypisana strategii, którą agent w niej zapisał. Każda tura z tego czatu MUST nieść kontekst otwartej strategii
(identyfikator, rewizję bazową i niezapisany tekst edytora). Po każdej turze zakładka MUST czytać strategię od nowa tak,
jak po turze panelu. Panel agenta terminala MUST działać jak dotąd, a czat strategii MUST NOT zmieniać jego otwartej
rozmowy ani stanu zwinięcia.

#### Scenario: Nowa strategia z opisu w oknie tworzenia

- **WHEN** operator klika „Nowa…” i opisuje strategię w czacie okna tworzenia
- **THEN** odpowiedź agenta MUST pojawić się w tym czacie, a po zapisie przez agenta okno MUST pokazać nową strategię
- **AND** ta rozmowa MUST zostać przypisana tej strategii

#### Scenario: Powrót do strategii

- **WHEN** operator otwiera strategię, o której rozmawiał wcześniej, także na innym urządzeniu
- **THEN** czat okna tworzenia MUST pokazać tamtą rozmowę

#### Scenario: Panel agenta obok

- **WHEN** operator pisze w czacie strategii, a w panelu agenta ma otwartą inną rozmowę
- **THEN** panel MUST dalej pokazywać swoją rozmowę i swój stan zwinięcia
