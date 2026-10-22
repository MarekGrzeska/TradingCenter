## MODIFIED Requirements

### Requirement: Odczyt ma stały kształt i stempel

Odczyt MUST nieść: krótkie streszczenie po polsku niezależnie od języka filmu, tekst odczytu w markdown, którego
układ i język wyznacza prompt, oraz ocenę wpływu 1–10. Odczyt MUST NOT nieść list tez, instrumentów, prognoz ani
tematów. Odczyt MUST nieść nazwę modelu, moment powstania oraz prompt i wersję promptu, którą powstał. Tekst
dłuższy niż limit ogłoszony przez kontrakt MUST zostać skrócony, nie odrzucony. Odpowiedź modelu niezgodna z tym
kształtem MUST NOT zostać zapisana. Odczyty zapisane w poprzednim kształcie MUST zostać przepisane do tego kształtu
tak, by ich streszczenie, ocena i treść tez, instrumentów i prognoz zostały zachowane w tekście.

#### Scenario: Model zwraca ocenę spoza zakresu

- **WHEN** model zwraca ocenę wpływu 12
- **THEN** odczyt MUST NOT zostać zapisany, a film MUST zostać spróbowany ponownie w kolejnym
  przebiegu

#### Scenario: Odczyt sprzed zmiany

- **WHEN** klient czyta film odczytany przed zmianą
- **THEN** odczyt MUST mieć streszczenie, ocenę i tekst zawierający jego dawne tezy, instrumenty i prognozy
