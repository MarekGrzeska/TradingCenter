## MODIFIED Requirements

### Requirement: Wiadomość prowadzi do filmu

Moduł MUST ogłosić typ zdarzenia „film odczytany” z atrybutami: kanał, temat (gdy film przyszedł z
tematu), tytuł, ocena wpływu, nazwa promptu, odnośnik do filmu na YouTube oraz gotowa treść powiadomienia.
Zdarzenie MUST NOT nieść instrumentów. Treść MUST nieść tytuł, kanał, ocenę wpływu, pełny tekst odczytu
promptem filmu i odnośnik, i MUST mieścić się w limicie treści zdarzenia.

#### Scenario: Odczyt z sekcjami

- **WHEN** prompt kanału każe ułożyć odczyt w sekcje, a model tak go napisał
- **THEN** treść powiadomienia MUST nieść ten tekst, a nie streszczenie

#### Scenario: Odczyt dłuższy niż limit zdarzenia

- **WHEN** tekst odczytu przekracza miejsce w treści zdarzenia
- **THEN** moduł MUST go skrócić sam ze znakiem cięcia, a odnośnik do filmu MUST zostać na końcu treści
