## Purpose

Zestaw narzędzi, które moduł publikuje klientowi MCP: co da się nimi przeczytać o rachunku, co
da się nimi na nim zmienić, czego w zestawie nie ma i po czym poznać, że narzędzie odmówiło,
a nie że nie dało się go zapytać.

## ADDED Requirements

### Requirement: Zestaw obejmuje rachunek i wykonanie, a nie rynek

Zestaw MUST pozwalać odczytać stan rachunku — otwarte pozycje, zlecenia oczekujące i saldo —
oraz wykonać na nim operacje: złożenie zlecenia, zamknięcie pozycji, zmianę dołączonych stopów
i anulowanie zlecenia oczekującego.

Zestaw MUST NOT publikować narzędzia odpowiadającego o cenach, świecach ani wskaźnikach. Cena
ma w tym systemie jedno źródło i jest nim archiwum; drugie źródło w tym samym przebiegu daje
ślad, w którym nie widać, na czym oparta była decyzja. Agent, który potrzebuje ceny, dostaje
narzędzie serwera odczytu — jawnie, jak każde inne.

#### Scenario: Model pyta o cenę instrumentu

- **WHEN** model szuka w tym zestawie narzędzia odpowiadającego o bieżącej cenie
- **THEN** takiego narzędzia nie ma
- **AND** opis zestawu nazywa archiwum jako miejsce, w którym pyta się o rynek

#### Scenario: Odczyt stanu rachunku

- **WHEN** klient MCP prosi o otwarte pozycje
- **THEN** każda pozycja niesie identyfikator, symbol, kierunek, wielkość, poziom otwarcia
  i wynik
- **AND** rachunek bez otwartych pozycji odpowiada pustą listą, a nie błędem

### Requirement: Narzędzie zapisujące jest oznaczone jako zmieniające stan

Każde narzędzie zmieniające stan rachunku MUST być tak oznaczone w tym, co moduł ogłasza,
a narzędzie wyłącznie czytające MUST być oznaczone jako czytające. Oznaczenie MUST być
zgodne z tym, co narzędzie robi.

Wywołujący, który dobiera agentom narzędzia, ma z ogłoszenia poznać, które z nich ruszają
pieniądze — bez czytania kodu tego modułu i bez zgadywania z nazwy.

#### Scenario: Klient czyta listę narzędzi

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** narzędzia składające zlecenie, zamykające pozycję, zmieniające stopy i anulujące
  zlecenie są oznaczone jako zmieniające stan
- **AND** narzędzia o pozycjach, zleceniach oczekujących i saldzie są oznaczone jako czytające

### Requirement: Odmowa narzędzia jest odróżnialna od awarii dostępu

Narzędzie, które nie może wykonać tego, o co poproszono, MUST odpowiedzieć odmową nazywającą
powód i to, co trzeba zmienić, żeby wywołanie się udało. Nieosiągalny gateway, przekroczony
czas oczekiwania i odrzucone poświadczenie MUST być zgłoszone jako awaria dostępu, a MUST NOT
być zgłoszone jako odmowa.

Model, który dostał odmowę, poprawia żądanie; model, który dostał awarię dostępu, nie ma czego
poprawiać. Zwinięcie jednego w drugie każe mu poprawiać zlecenie, z którym nic nie było nie
tak.

#### Scenario: Zlecenie oczekujące bez poziomu docelowego

- **WHEN** model składa zlecenie LIMIT bez poziomu docelowego
- **THEN** narzędzie odmawia, nazywając brakujące pole
- **AND** żadne żądanie nie zostaje wysłane do gatewaya

#### Scenario: Gateway nie odpowiada

- **WHEN** wywołanie narzędzia przekracza dozwolony czas oczekiwania na gateway
- **THEN** model dostaje wynik nazywający awarię dostępu
- **AND** wynik MUST NOT sugerować, że zlecenie zostało odrzucone

### Requirement: Nieznany symbol jest odmową przed dotknięciem rachunku

Narzędzie zapisujące MUST odrzucić żądanie wskazujące symbol, którego provider nie zna albo
którym nie da się handlować, zanim cokolwiek zostanie złożone. Odmowa MUST nazywać symbol.

#### Scenario: Zlecenie na symbol spoza providera

- **WHEN** model składa zlecenie na symbol, którego provider nie publikuje
- **THEN** narzędzie odmawia, nazywając symbol
- **AND** na rachunku nic się nie zmienia
