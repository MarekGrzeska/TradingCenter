## Purpose

Sekcja **Prompt management** na stronie Agent Settings, gdzie operator ogląda i edytuje
system prompt agenta wprost z terminala, bez commitu i deployu.

## ADDED Requirements

### Requirement: Sekcja pokazuje aktualną treść i wersję z modułu

Sekcja MUST pokazywać aktualną treść obu wariantów promptu i ich wspólną wersję,
odczytane z modułu agenta — nie z wartości zapamiętanej wcześniej w przeglądarce.

#### Scenario: Rozwinięcie sekcji

- **WHEN** operator rozwija sekcję Prompt management
- **THEN** widzi aktualną treść obu wariantów i numer wersji, tak jak zwrócił je moduł

### Requirement: Zapis wysyła oba warianty i pokazuje wersję zwróconą przez moduł

Zapis w sekcji MUST wysłać do modułu agenta oba warianty naraz. Po powodzeniu sekcja
MUST pokazać wersję zwróconą przez moduł. Terminal MUST NOT liczyć ani zgadywać numeru
nowej wersji po swojej stronie.

#### Scenario: Zapis zmiany

- **WHEN** operator zmienia tekst jednego lub obu wariantów i zapisuje
- **THEN** sekcja pokazuje treść i wersję, które zwrócił moduł w odpowiedzi na zapis

#### Scenario: Moduł odrzuca pusty tekst

- **WHEN** operator próbuje zapisać pusty tekst jednego z wariantów
- **THEN** sekcja pokazuje odmowę modułu
- **AND** MUST NOT podmienić wyświetlanej treści na pustą

### Requirement: Moduł nieosiągalny nie pokazuje żadnej treści jako aktualnej

Gdy moduł agenta nie odpowiada na odczyt, sekcja MUST powiedzieć to wprost i MUST NOT
pokazać żadnej treści promptu tak, jakby była aktualna.

#### Scenario: Moduł agenta nie odpowiada na odczyt

- **WHEN** moduł agenta nie odpowiada podczas otwierania sekcji
- **THEN** sekcja mówi to wprost
- **AND** MUST NOT pokazywać żadnej treści promptu jako aktualnej
