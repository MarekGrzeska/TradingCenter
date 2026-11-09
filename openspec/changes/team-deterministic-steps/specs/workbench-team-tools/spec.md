## ADDED Requirements

### Requirement: Zestaw składa zespoły z krokami

Zestaw MUST pozwalać jednym wywołaniem:
- założyć zespół z krokami i agentami;
- poprawić kroki istniejącego zespołu: podmienić krok o tym samym kluczu, dołożyć nowy, usunąć wskazany. Poprawka
  MUST zachować kroki i agentów, których nie nazwała.

Odczyt zespołu MUST pokazywać jego kroki z parametrami. Zestaw MUST mieć narzędzie czytające katalog przepisów: nazwy,
opisy, parametry i potrzebne narzędzia. Opisy narzędzi MUST mówić, że krok nie woła modelu, a jego wynik czyta
następnik.

Odmowa zapisu kroku przez `teams` MUST dotrzeć do modelu z nazwą kroku, a MUST NOT zostać zastąpiona komunikatem
ogólnym.

#### Scenario: Zespół z krokiem założony z Telegrama

- **WHEN** operator prosi agenta na Telegramie o zespół z krokiem `strategy_execute` i reporterem
- **THEN** model zakłada go jednym wywołaniem
- **AND** zespół należy do operatora i jest widoczny w terminalu z krokiem na obrazie

#### Scenario: Poprawka parametru kroku

- **WHEN** model zmienia rozmiar w kroku istniejącego zespołu
- **THEN** powstaje nowa rewizja z nowym rozmiarem
- **AND** agenci i pozostałe kroki są w niej niezmienieni

### Requirement: Zestaw ustawia konto demo i granice handlowe, ale nie konto realne

Narzędzia zakładające i poprawiające zespół MUST pozwalać ustawić konto demo zespołu i jego granice handlowe. MUST NOT
pozwalać ustawić konta realnego. Zespół na koncie realnym MUST móc być poprawiany przez zestaw w agentach, krokach,
zależnościach i granicach kosztu, a jego sekcja handlowa MUST przechodzić do nowej rewizji bez zmian. Próba zmiany
sekcji handlowej takiego zespołu MUST zostać odmówiona z powodem nazywającym terminal jako miejsce tej zmiany.

To jedyny zamierzony wyjątek od zasady, że czynność dostępna w terminalu jest dostępna z czatu. Przełączenie zespołu
na prawdziwe pieniądze zostaje czynnością operatora w jego własnym oknie, a nie zdaniem, które model może źle
zrozumieć.

#### Scenario: Zespół demo z kontem z czatu

- **WHEN** model zakłada zespół z kontem demo i granicą liczby zleceń na dobę
- **THEN** rewizja niesie to konto i tę granicę

#### Scenario: Próba ustawienia konta realnego

- **WHEN** model zakłada zespół ze środowiskiem konta realnego
- **THEN** zapis zostaje odmówiony
- **AND** odmowa mówi, że konto realne ustawia się w terminalu

#### Scenario: Poprawka zespołu na koncie realnym

- **WHEN** model poprawia agenta w zespole, któremu operator ustawił w terminalu konto realne
- **THEN** nowa rewizja niesie tę samą sekcję handlową co poprzednia
