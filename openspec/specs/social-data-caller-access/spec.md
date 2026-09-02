# social-data-caller-access Specification

## Purpose
Kto sięga po którą powierzchnię modułu — trasa narzędziowa dla workbencha, REST dla terminala
i pocketa — i dlaczego przepuszczenie przez bramę platformy samo w sobie niczego nie rozstrzyga,
skoro obie powierzchnie stoją w jednej aplikacji.

## Requirements

### Requirement: Żądanie z sieci niesie tożsamość wołającego

Moduł MUST wymagać tożsamości od żądania przychodzącego po sieci i MUST odmówić żądaniu, które jej
nie niesie. Wyłączenie tego wymogu MUST być możliwe wyłącznie dla pracy lokalnej i MUST być
widoczne w logu startu.

#### Scenario: Żądanie bez tożsamości we wdrożeniu

- **WHEN** żądanie dociera do modułu bez tożsamości wołającego
- **THEN** moduł MUST odmówić, zanim dotknie archiwum

### Requirement: Tożsamość rozstrzyga, po którą powierzchnię wolno sięgnąć

Sama obecność tożsamości MUST NOT wystarczać do sięgnięcia po dowolną trasę. Moduł MUST trzymać
własny zapis tego, która tożsamość ma prawo do której powierzchni, i MUST odmówić żądaniu spoza
tego zapisu. Ścieżka, której zapis nie wymienia, MUST być odmawiana, a nie przepuszczana.

Brama platformy autoryzuje aplikację, nie trasę: wołający wpuszczony do narzędzi byłby bez tego
zapisu za wszystkimi trasami REST tej samej aplikacji.

#### Scenario: Wołający narzędzi sięga po REST

- **WHEN** tożsamość dopuszczona do trasy narzędziowej woła trasę kontraktu REST
- **THEN** moduł MUST odmówić

#### Scenario: Ścieżka spoza zapisu

- **WHEN** żądanie trafia na ścieżkę, której zapis nie wymienia
- **THEN** moduł MUST odmówić

### Requirement: Rozpoznawana jest aplikacja, nie osoba

Zapis dostępu MUST wymieniać identyfikatory **aplikacji**, a moduł MUST czytać je z odpowiedniego
oświadczenia w tokenie. Identyfikator zalogowanej osoby MUST NOT być używany do rozstrzygnięcia,
czy wołający ma prawo do powierzchni.

#### Scenario: Token delegowany operatora

- **WHEN** terminal woła kontrakt tokenem wystawionym w imieniu operatora
- **THEN** moduł MUST rozstrzygać po identyfikatorze aplikacji, nie po identyfikatorze osoby

### Requirement: Pusty zapis odmawia wszystkim

Świeże wdrożenie, w którym zapis dostępu jest pusty, MUST odmawiać każdemu wołającemu z sieci.
Ustawienia wpuszczające workbench MUST dojechać do aplikacji przed obrazem, który ten zapis
egzekwuje — inaczej między wdrożeniem a `apply` jest przerwa w działaniu, a nie łagodne przejście.

#### Scenario: Wdrożenie przed konfiguracją

- **WHEN** moduł wstaje z pustym zapisem dostępu
- **THEN** MUST odmawiać wołaniom z sieci, zamiast wpuszczać kogokolwiek domyślnie

### Requirement: Zdrowie modułu da się sprawdzić bez tożsamości

Moduł MUST odpowiadać na sondę zdrowia bez tożsamości wołającego i bez nawiązywania sesji MCP.
Odpowiedź MUST nazywać moduł, żeby sonda wdrożenia potrafiła odróżnić właściwą aplikację od cudzej
odpowiadającej pod tym samym adresem.

#### Scenario: Sonda po wdrożeniu

- **WHEN** sonda wdrożenia pyta o zdrowie modułu
- **THEN** odpowiedź MUST przyjść bez tożsamości i MUST nieść nazwę modułu
