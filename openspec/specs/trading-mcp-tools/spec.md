# trading-mcp-tools Specification

## Purpose
Zestaw narzędzi, które moduł publikuje klientowi MCP: co da się nimi przeczytać o rachunku, co
da się nimi na nim zmienić, czego w zestawie nie ma i po czym poznać, że narzędzie odmówiło,
a nie że nie dało się go zapytać.
## Requirements
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

### Requirement: Zestaw podaje warunki instrumentu, na których liczy się rozmiar

Zestaw MUST publikować narzędzie czytające warunki handlowe instrumentu: wymóg depozytu wraz
z jednostką, najmniejszy i największy dopuszczalny rozmiar zlecenia, krok rozmiaru, wielkość
lota i walutę rozliczenia. Narzędzie MUST być oznaczone jako czytające.

Model nie ma jak sprawdzić tych liczb ani ich wyliczyć z czegokolwiek, co już widzi. Rozmiar
podany w zleceniu jest wobec nich milcząco korygowany przez providera — rozmiar poniżej kroku
zostaje ścięty, a odpowiedź nie mówi, że to się stało.

Narzędzie MUST NOT odpowiadać ceną. To ta sama granica, którą zestaw trzyma wobec świec
i wskaźników: o rynek pyta się archiwum.

#### Scenario: Model czyta warunki instrumentu

- **WHEN** model prosi o warunki handlowe instrumentu
- **THEN** dostaje wymóg depozytu z jednostką, najmniejszy i największy rozmiar, krok rozmiaru,
  wielkość lota i walutę
- **AND** odpowiedź MUST NOT zawierać bieżącej ceny

#### Scenario: Warunki instrumentu spoza providera

- **WHEN** model prosi o warunki symbolu, którego provider nie zna
- **THEN** narzędzie odmawia, nazywając symbol

### Requirement: Rozmiar wynikający z zadanej marży liczy moduł, nie model

Zestaw MUST publikować narzędzie czytające, które z zadanej kwoty depozytu, ceny podanej przez
wywołującego i warunków instrumentu wylicza rozmiar zlecenia. Wynik MUST nieść rozmiar
zaokrąglony **w dół** do kroku dopuszczonego przez providera, kwotę depozytu, jaką ten rozmiar
naprawdę zajmie, oraz wartość kontraktu, jaką otwiera. Narzędzie MUST być oznaczone jako
czytające i MUST NOT składać zlecenia.

Cena MUST być argumentem, a nie czymś, co moduł czyta sam. Zlecenie ma być rozliczalne z tym,
co model widział w archiwum, a cena wzięta tu po cichu byłaby drugim źródłem w tym samym
przebiegu — dokładnie tym, czego zestaw nie robi dla świec.

Zaokrąglenie MUST iść w dół, nie do najbliższego kroku. Rozmiar w górę zajmuje więcej depozytu,
niż wywołujący zadał, a granica, którą da się przekroczyć zaokrągleniem, nie jest granicą.

Narzędzie MUST NOT podpowiadać kierunku ani tego, czy zlecenie warto złożyć. Liczy warunki,
których model nie ma jak sprawdzić, i na tym kończy się jego udział w decyzji.

#### Scenario: Depozyt przeliczony na rozmiar

- **WHEN** model podaje symbol, kwotę depozytu i cenę
- **THEN** dostaje rozmiar mieszczący się w kroku providera, zajmowany depozyt i wartość
  otwieranego kontraktu
- **AND** zajmowany depozyt MUST NOT być większy od zadanej kwoty

#### Scenario: Zadana kwota nie starcza na najmniejsze zlecenie

- **WHEN** wyliczony rozmiar wypada poniżej najmniejszego dopuszczalnego
- **THEN** narzędzie odmawia, podając najmniejszy dopuszczalny rozmiar i depozyt, jakiego by
  wymagał
- **AND** MUST NOT zwracać rozmiaru, którego provider by nie przyjął

#### Scenario: Zadana kwota przekracza największe dopuszczalne zlecenie

- **WHEN** wyliczony rozmiar wypada powyżej największego dopuszczalnego
- **THEN** narzędzie odmawia, podając największy dopuszczalny rozmiar

#### Scenario: Jednostka wymogu depozytu jest nieznana modułowi

- **WHEN** provider podaje wymóg depozytu w jednostce, której moduł nie umie przeliczyć
- **THEN** narzędzie odmawia, nazywając jednostkę
- **AND** MUST NOT zgadywać, że chodziło o procent

### Requirement: Opis narzędzia jest częścią kontraktu

Opis narzędzia jest jedyną rzeczą, którą model o nim wie, zanim je zawoła, więc MUST być
traktowany jak kontrakt, a nie jak komentarz. Każde publikowane narzędzie MUST nieść opis,
typowane parametry i jawnie nazwane jednostki — rozmiar, poziom ceny i walutę, w której
podawane są saldo i wynik.

W module, którego narzędzia ruszają rachunek, przemilczana jednostka nie jest
niedopowiedzeniem: rozmiar wzięty za kontrakty zamiast za jednostki instrumentu jest
zleceniem o innej wielkości, złożonym bez błędu.

#### Scenario: Narzędzie bez nazwanych jednostek

- **WHEN** do zestawu trafia narzędzie zapisujące bez opisu albo bez nazwanej jednostki
  rozmiaru
- **THEN** MUST to wywrócić test powierzchni narzędzi, zanim moduł zostanie wdrożony

### Requirement: Powierzchnia narzędzi ma zapisany sufit

Cały zestaw — opisy, schematy wejścia i schematy wyjścia razem — jest czytany przez model w
**każdej** turze rozmowy, więc jego rozmiar jest kosztem, nie szczegółem implementacji.
Moduł MUST trzymać zserializowaną postać tego, co ogłasza, poniżej sufitu zapisanego w jego
własnym teście, i MUST wywrócić ten test, gdy sufit zostanie przekroczony.

Moduł MUST NOT publikować w schemacie rzeczy, które nie niosą modelowi informacji ponad to,
co sam schemat już mówi.

#### Scenario: Zestaw urósł ponad sufit

- **WHEN** zmiana dokłada narzędzie, pole albo akapit opisu, po którym zserializowany
  zestaw przekracza sufit
- **THEN** test powierzchni narzędzi MUST wywrócić się, nazywając zmierzoną wielkość i sufit
- **AND** moduł MUST NOT zostać wdrożony, dopóki jedno z dwóch nie zostanie zmienione świadomie

#### Scenario: Schemat bez rusztowania

- **WHEN** model czyta ogłoszony schemat narzędzia
- **THEN** schemat MUST NOT nieść nazw pól powtórzonych jako ich własne etykiety ani
  wartości domyślnych dla odpowiedzi, której model nie konstruuje
- **AND** MUST nadal nieść każde pole, jego typ i to, czy jest wymagane
