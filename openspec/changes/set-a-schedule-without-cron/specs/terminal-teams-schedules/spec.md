## ADDED Requirements

### Requirement: Harmonogram układa się rytmem i godziną, nie wyrażeniem czasowym

Terminal MUST pozwalać ułożyć harmonogram przez wybór rytmu (co N minut, co godzinę,
codziennie, w wybrane dni tygodnia, w wybrany dzień miesiąca) i godziny, bez wpisywania
wyrażenia czasowego. Wyrażenie czasowe MUST pozostać dostępne jako droga dla rytmu, którego
kreator nie obejmuje, i MUST być schowane poza domyślnym widokiem formularza. Harmonogram,
którego wyrażenia nie da się opisać żadnym rytmem, MUST być pokazany tym wyrażeniem i MUST
dać się edytować bez utraty tego, co niesie.

Zespół układa operator rynku, nie administrator systemu. Pole z pięcioma gwiazdkami jest
dla niego zamkniętymi drzwiami, a wpisane w nie na wyczucie wyrażenie jest gorsze niż brak
harmonogramu, bo wygląda na działające.

#### Scenario: Harmonogram codzienny

- **WHEN** operator wybiera rytm „codziennie" i godzinę 9:00
- **THEN** zapisany harmonogram wyzwala się codziennie o 9:00 czasu polskiego
- **AND** operator nie wpisał żadnego wyrażenia czasowego

#### Scenario: Rytm spoza kreatora

- **WHEN** operator otwiera harmonogram, którego wyrażenia kreator nie obejmuje
- **THEN** widzi to wyrażenie i może je poprawić
- **AND** zapis nie zamienia go na inny rytm

### Requirement: Operator widzi skutek harmonogramu przed zapisaniem go

Terminal MUST pokazywać najbliższe wyzwolenia układanego harmonogramu, zanim zostanie
zapisany, i MUST je odświeżać po zmianie rytmu lub godziny. Te momenty MUST pochodzić
z modułu.

#### Scenario: Podgląd w trakcie układania

- **WHEN** operator zmienia godzinę w kreatorze harmonogramu
- **THEN** widzi najbliższe wyzwolenia dla tej godziny, przed zapisaniem harmonogramu

## MODIFIED Requirements

### Requirement: Terminal nie liczy czasu wyzwolenia sam

Momenty najbliższych wyzwoleń MUST pochodzić z modułu. Terminal MUST NOT nosić własnego
parsera wyrażeń czasowych, własnej implementacji ich rozwijania ani własnej zamiany rytmu
na wyrażenie czasowe.

To ta sama zasada, co przy katalogu modeli i katalogu narzędzi: druga implementacja tej samej
reguły po stronie terminala rozjeżdża się z pierwszą, a operator widzi wtedy inną godzinę niż
ta, o której moduł naprawdę ruszy.

#### Scenario: Podgląd najbliższych wyzwoleń

- **WHEN** operator układa harmonogram i chce zobaczyć, kiedy ten wyzwoli
- **THEN** pokazane momenty pochodzą z odpowiedzi modułu

#### Scenario: Rytm zamieniany na wyrażenie czasowe

- **WHEN** operator zapisuje harmonogram ułożony rytmem
- **THEN** zamiany na wyrażenie czasowe dokonuje moduł

### Requirement: Czas jest pokazany tak, żeby nie trzeba było go przeliczać

Moment wyzwolenia MUST być pokazany w czasie polskim i MUST być oznaczony jako czas polski.
Gdy strefa przeglądarki jest inna niż polska, ten sam moment MUST być pokazany obok także
w czasie przeglądarki.

Harmonogramy są opisywane w czasie polskim, więc to on jest tu czasem, w którym operator
myśli. UTC był tu wcześniej dlatego, że w nim liczył moduł — a nie dlatego, że ktoś go
czytał.

#### Scenario: Operator w strefie polskiej

- **WHEN** terminal pokazuje moment najbliższego wyzwolenia operatorowi w strefie polskiej
- **THEN** widzi ten moment raz, oznaczony jako czas polski

#### Scenario: Operator w innej strefie

- **WHEN** terminal pokazuje moment najbliższego wyzwolenia operatorowi poza strefą polską
- **THEN** widzi go w czasie polskim i w czasie swojej przeglądarki
