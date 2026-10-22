## Purpose

Reguła powiadomienia: jedyne miejsce, w którym operator mówi, kiedy, o czym i komu system ma dać znać,
oraz zasady jej zapisu, które nie przepuszczają reguły, która nigdy by nie zadziałała.

## ADDED Requirements

### Requirement: Reguła składa się ze źródła, filtra, adresata, szablonu i rytmu

Reguła MUST nieść: nazwę nadaną przez operatora, dokładnie jedno źródło (stan albo zdarzenie), filtr
właściwy temu źródłu, nazwę adresata bramy Telegrama, szablon treści, czas martwy oraz tryb
jednorazowy albo powtarzalny. Reguła MUST NOT nieść identyfikatora czatu ani nazwy bota.

#### Scenario: Reguła ze źródłem stanu

- **WHEN** operator zapisuje regułę „cena EURUSD powyżej 1,10” z adresatem i czasem martwym
- **THEN** reguła MUST zostać zapisana jako reguła stanu i MUST pojawić się na liście reguł jako włączona

#### Scenario: Reguła z dwoma źródłami

- **WHEN** operator zapisuje regułę, która podaje i warunek stanu, i typ zdarzenia
- **THEN** zapis MUST zostać odrzucony z powodem nazywającym oba źródła

### Requirement: Zapis odrzuca regułę, która nie mogłaby zadziałać

Zapis reguły MUST zostać odrzucony z powodem nazywającym wadliwe pole, gdy reguła wskazuje
narzędzie, którego katalog nie ogłasza, narzędzie zapisujące, argument spoza schematu narzędzia,
pole wyniku, które według schematu nie jest liczbą, typ zdarzenia, którego nikt nie ogłosił, atrybut
spoza schematu typu zdarzenia, porównanie niepasujące do typu atrybutu albo szablon odwołujący się do
nieznanego pola. Ta sama walidacja MUST obowiązywać przy zapisie i przy szkicu ze zdania.

Literówka przyjęta przy zapisie jest regułą, która milczy zawsze. Taka reguła wygląda tak samo jak
reguła, której warunek po prostu się nie spełnił.

#### Scenario: Pole wyniku, które nie jest liczbą

- **WHEN** operator zapisuje regułę stanu porównującą pole tekstowe z liczbą
- **THEN** zapis MUST zostać odrzucony z powodem nazywającym to pole

#### Scenario: Nieogłoszony typ zdarzenia

- **WHEN** operator zapisuje regułę zdarzenia z typem, którego żaden pakiet nie ogłosił
- **THEN** zapis MUST zostać odrzucony z powodem nazywającym ten typ

### Requirement: Adresat nieistniejący przy zapisie jest odmową, a znikający później — stanem reguły

Zapis reguły z adresatem, którego brama nie zna, MUST zostać odrzucony. Gdy adresat zniknie po
zapisie, reguła MUST pozostać zapisana, jej odpalenia MUST być zapisywane jako nieudane z powodem
„adresat nie istnieje”, a lista reguł MUST to pokazywać.

#### Scenario: Adresat usunięty w zakładce Telegram

- **WHEN** operator usuwa adresata, na którego wskazuje reguła, a reguła potem odpala
- **THEN** odpalenie MUST zostać zapisane jako nieudane z powodem nazywającym adresata
- **AND** reguła MUST być oznaczona na liście jako wskazująca na nieistniejącego adresata

### Requirement: Reguły zmienia tylko operator

Reguły MUST być tworzone, zmieniane, włączane, wyłączane i usuwane wyłącznie przez kontrakt REST.
Powierzchnia narzędziowa MAY wyliczać reguły i ich odpalenia, ale MUST NOT ich zmieniać.

Reguła przeżywa rozmowę, która by ją zmieniła. Kto zmienia reguły, ten może przekierować alerty do
kogokolwiek, z kim rozmowa akurat rozmawiała.

#### Scenario: Model szuka narzędzia zapisującego regułę

- **WHEN** przeszukuje się powierzchnię narzędziową pakietu alertów
- **THEN** MUST NOT znaleźć się w niej narzędzie tworzące, zmieniające ani usuwające reguły

### Requirement: Reguła jednorazowa wyłącza się po pierwszym doręczeniu

Reguła w trybie jednorazowym MUST wyłączyć się sama po pierwszym udanym doręczeniu, z powodem
mówiącym, że odpaliła. Reguła powtarzalna MUST pozostać włączona i MUST podlegać czasowi martwemu.

#### Scenario: Alert cenowy jednorazowy

- **WHEN** jednorazowa reguła „EURUSD powyżej 1,10” odpala i wiadomość zostaje doręczona
- **THEN** reguła MUST być wyłączona z powodem „odpaliła”
- **AND** kolejne przekroczenie progu MUST NOT dać wiadomości
