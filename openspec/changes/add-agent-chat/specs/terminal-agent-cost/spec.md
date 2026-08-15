## Purpose

Opisuje zakładkę **Agents cost** — miejsce, w którym operator sprawdza, ile rozmowy z
agentem kosztowały, zanim dowie się tego z faktury Azure.

## ADDED Requirements

### Requirement: Zakładka pokazuje koszt w trzech przekrojach

Zakładka MUST pokazywać zużycie i koszt w podziale na model, w podziale na rozmowę i w
czasie, dla wybranego zakresu dat. Trzy przekroje odpowiadają na trzy różne pytania — „czy
najdroższy model zarabia na siebie", „która rozmowa tyle kosztowała" i „czy to rośnie" — i
żaden nie odpowiada za pozostałe.

Koszt i tokeny MUST być pokazane osobno. Zakładka MUST pokazywać sumę kosztu dla wybranego
zakresu w jednym miejscu; suma rozproszona po tabeli nie jest odpowiedzią na pytanie, po
które operator tu wchodzi.

#### Scenario: Koszt w podziale na model

- **WHEN** operator otwiera zakładkę
- **THEN** widzi dla każdego modelu tokeny i koszt z wybranego zakresu
- **AND** widzi sumę kosztu dla całego zakresu

#### Scenario: Przejście do rozmowy

- **WHEN** operator wskazuje rozmowę na liście kosztów
- **THEN** widzi jej koszt rozbity na wywołania

#### Scenario: Zakres bez rozmów

- **WHEN** wybrany zakres nie obejmuje żadnej rozmowy
- **THEN** zakładka mówi, że w tym zakresie nic nie zużyto
- **AND** MUST NOT pokazywać pustej tabeli bez wyjaśnienia

### Requirement: Liczby pochodzą z modułu, nie z przeglądarki

Zakładka MUST pokazywać wartości policzone przez moduł agenta. Terminal MUST NOT liczyć
kosztu z tokenów i cennika po swojej stronie — cennik zmieniał się już po fakcie i
przeliczenie w przeglądarce rozjechałoby się z tym, co zapisano przy wywołaniu, a to
zapisane jest tym, co zgadza się z fakturą.

Zużycie oznaczone przez moduł jako nieznane MUST NOT być wliczane do sumy jako zero —
suma MUST pozostać dokładnie tym, co moduł policzył z wierszy o znanej cenie. Zakładka
MUST NOT pokazywać operatorowi, ile wierszy było nieznanych: to policzenie kosztu i sumy
jest jedynym, co ta zakładka odpowiada, a licznik "+N unknown" był szumem obok niego, nie
odpowiedzią na inne pytanie (decyzja operatora, 2026-08-15 — wcześniej ten sam wiersz
wymagał odwrotnie).

#### Scenario: Zużycie nieznane

- **WHEN** wśród wierszy zakresu są takie, dla których dostawca nie podał zużycia
- **THEN** suma i koszt wiersza pomijają je tak, jakby ich nie było w tym zakresie
- **AND** zakładka nie pokazuje żadnego licznika ani etykiety dla nich

#### Scenario: Moduł agenta jest nieosiągalny

- **WHEN** moduł agenta nie odpowiada
- **THEN** zakładka mówi to wprost
- **AND** MUST NOT pokazywać liczb sprzed awarii jako bieżących
