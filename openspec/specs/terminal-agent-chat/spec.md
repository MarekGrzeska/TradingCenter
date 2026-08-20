# terminal-agent-chat Specification

## Purpose

Opisuje panel agenta w terminalu jako rzecz, z której operator korzysta: gdzie wisi, jak
przełącza się między rozmowami, jak wybiera model i co widzi, gdy odpowiedź jeszcze
płynie albo już się nie uda.
## Requirements
### Requirement: Panel należy do terminala, nie do zakładki

Panel agenta MUST być dostępny z każdej zakładki i MUST NOT gubić rozmowy przy jej zmianie:
przejście z wykresu do historii zbierania MUST zostawić transkrypt tam, gdzie był, łącznie
z odpowiedzią, która w tej chwili płynie. Panel rozwinięty MUST odsuwać treść zakładki, a
nie ją zakrywać — operator czyta wykres i rozmowę naraz, bo o wykres pyta.

Stan zwinięcia MUST przetrwać przeładowanie terminala: panel zabiera szerokość wykresom i
operator, który go zamknął, MUST NOT zastać go otwartym.

#### Scenario: Zmiana zakładki w trakcie odpowiedzi

- **WHEN** operator zmienia zakładkę, gdy odpowiedź agenta jeszcze płynie
- **THEN** panel zostaje na ekranie z tą samą rozmową
- **AND** odpowiedź płynie dalej do tego samego dymka

#### Scenario: Przeładowanie terminala

- **WHEN** operator zwija panel i przeładowuje terminal
- **THEN** panel jest zwinięty

### Requirement: Operator wybiera rozmowę albo zaczyna nową

Panel MUST pokazywać listę wcześniejszych rozmów operatora, uporządkowaną od ostatnio
używanej, i MUST pozwalać otworzyć każdą z nich oraz zacząć nową. Otwarcie rozmowy MUST
wczytać jej transkrypt z modułu — transkrypt jest po stronie modułu i przeglądarka MUST NOT
być jego jedynym źródłem.

Terminal MUST pamiętać, która rozmowa była otwarta, i wracać do niej po przeładowaniu.
Operator, który po każdym odświeżeniu ląduje w pustej rozmowie, przestaje panelu używać.

#### Scenario: Powrót do wcześniejszej rozmowy

- **WHEN** operator wybiera rozmowę z listy
- **THEN** panel pokazuje jej transkrypt wczytany z modułu
- **AND** kolejna wypowiedź dopisuje się do tej rozmowy

#### Scenario: Nowa rozmowa

- **WHEN** operator zaczyna nową rozmowę
- **THEN** panel pokazuje pusty transkrypt
- **AND** rozmowa pojawia się na liście dopiero po pierwszej wymianie zdań

#### Scenario: Przeładowanie z otwartą rozmową

- **WHEN** operator przeładowuje terminal z otwartą rozmową
- **THEN** panel wraca do tej samej rozmowy

### Requirement: Model wybiera się w oknie agenta

Panel MUST pozwalać wybrać model dla rozmowy spośród tych, które moduł publikuje, i MUST
pokazywać, którym modelem rozmowa jest prowadzona. Wybierak MUST być zbudowany z katalogu
modułu — terminal MUST NOT nieść listy modeli we własnym kodzie.

Wybierak MUST pokazywać różnicę kosztu między modelami. Wybór między trzema nazwami bez tej
informacji jest zgadywaniem, a różnica między najtańszym a najdroższym jest
dwudziestopięciokrotna.

#### Scenario: Wybór modelu przed pytaniem

- **WHEN** operator wybiera model i wysyła wiadomość
- **THEN** odpowiedź powstaje na wybranym modelu

#### Scenario: Katalog niedostępny

- **WHEN** katalog modeli nie daje się wczytać
- **THEN** panel mówi, że wyboru modelu nie da się teraz pokazać
- **AND** MUST NOT podstawiać listy modeli z własnego kodu

### Requirement: Widać, że odpowiedź powstaje

Panel MUST pokazywać odpowiedź w miarę, jak przychodzi, a przed pierwszym jej fragmentem
MUST pokazywać, że wypowiedź została przyjęta i czekanie trwa. Operator MUST NOT stać przed
niezmienionym ekranem, na którym równie dobrze mogło nic się nie wysłać.

Panel MUST pokazywać wywołania narzędzi, którymi agent doszedł do odpowiedzi — w trakcie
tury, w chwili gdy przychodzą, i po powrocie do sesji, z transkryptu. Wywołanie MUST stać w
transkrypcie tam, gdzie padło, a nie w osobnym oknie diagnostycznym: to część drogi do
odpowiedzi, a nie zapis techniczny obok niej.

Wpis wywołania MUST nieść nazwę narzędzia i to, jak się skończyło, w postaci zwiniętej, i
MUST dać się rozwinąć do argumentów oraz treści wyniku albo powodu odmowy. Zwinięta postać
jest domyślna: tura z ośmioma wywołaniami rozwiniętymi zasłoniłaby rozmowę, o którą
operatorowi chodzi.

Wywołanie odmówione MUST być widoczne jako odmowa, odróżnialne od wywołania udanego i od
wywołania, którego serwer narzędzi nie przyjął. Odmowa narzędzia MUST NOT być pokazana jako
błąd całej odpowiedzi.

Zerwanie strumienia MUST być widoczne jako błąd, odróżnialny od odpowiedzi zakończonej.
Odpowiedź niepełna MUST być oznaczona jako niepełna, a nie pokazana jako całość. Odpowiedź
zatrzymana przez operatora MUST być odróżnialna od obu: nie jest błędem i nie jest urwana
sama z siebie — skończyła się, bo ktoś tak powiedział.

#### Scenario: Odpowiedź w trakcie

- **WHEN** operator wysyła wiadomość
- **THEN** panel pokazuje, że odpowiedź powstaje, zanim przyjdzie jej pierwszy fragment
- **AND** dopisuje kolejne fragmenty w miarę, jak przychodzą

#### Scenario: Narzędzie w trakcie tury

- **WHEN** agent wywołuje narzędzie w trakcie powstawania odpowiedzi
- **THEN** panel pokazuje wpis tego wywołania, zanim przyjdzie domknięcie odpowiedzi
- **AND** wpis niesie nazwę narzędzia i to, jak się skończyło

#### Scenario: Operator rozwija wywołanie

- **WHEN** operator rozwija wpis wywołania
- **THEN** widzi argumenty, którymi narzędzie wywołano, i treść wyniku albo powód odmowy

#### Scenario: Narzędzie odmawia

- **WHEN** narzędzie odmawia odpowiedzi
- **THEN** panel pokazuje wpis oznaczony jako odmowa, z jej powodem po rozwinięciu
- **AND** odpowiedź agenta MUST NOT zostać oznaczona jako niepełna wyłącznie z tego powodu

#### Scenario: Powrót do zakończonej rozmowy

- **WHEN** operator otwiera sesję, w której agent sięgał po narzędzia
- **THEN** panel pokazuje te same wywołania, które pokazywał w trakcie tury

#### Scenario: Strumień pęka

- **WHEN** strumień zostaje zerwany przed zakończeniem odpowiedzi
- **THEN** panel oznacza odpowiedź jako niepełną i podaje, że wystąpił błąd
- **AND** to, co dotarło, zostaje na ekranie

#### Scenario: Odpowiedź zatrzymana nie jest błędem

- **WHEN** tura kończy się zatrzymaniem na żądanie operatora
- **THEN** panel oznacza tę wypowiedź jako zatrzymaną
- **AND** MUST NOT pokazać jej jako błędu ani jako odpowiedzi zakończonej normalnie

#### Scenario: Moduł agenta jest nieosiągalny

- **WHEN** moduł agenta nie odpowiada
- **THEN** panel mówi to wprost
- **AND** MUST NOT pokazywać wypowiedzi agenta, która nie powstała

### Requirement: Lista rozmów pozwala je nazwać i usunąć

Terminal MUST pozwalać operatorowi zmienić nazwę rozmowy i usunąć rozmowę wprost z listy —
tam, gdzie operator ją widzi i tam, gdzie odróżnia ją od pozostałych.

Usunięcie MUST wymagać potwierdzenia. Lista rozmów jest czytana znacznie częściej, niż
zmieniana, a jedno chybione kliknięcie MUST NOT kosztować rozmowy.

Terminal MUST pokazać nazwę, którą moduł potwierdził, a nie tę, którą operator wpisał:
nazwa odrzucona albo nieprzyjęta z powodu awarii MUST NOT zostać na ekranie jako obowiązująca.

Usunięcie rozmowy otwartej w panelu MUST zamknąć jej transkrypt — panel MUST NOT pokazywać
rozmowy, której moduł już nie wydaje.

#### Scenario: Zmiana nazwy z listy

- **WHEN** operator zmienia nazwę rozmowy na liście i zatwierdza ją
- **THEN** lista pokazuje nową nazwę
- **AND** nazwa pochodzi z odpowiedzi modułu, nie z pola, które operator wypełnił

#### Scenario: Nazwa, której moduł nie przyjął

- **WHEN** operator zmienia nazwę rozmowy, a moduł odmawia albo jest nieosiągalny
- **THEN** lista pokazuje nazwę sprzed próby

#### Scenario: Usunięcie wymaga potwierdzenia

- **WHEN** operator wybiera usunięcie rozmowy
- **THEN** terminal pyta o potwierdzenie, zanim cokolwiek usunie
- **AND** rezygnacja zostawia rozmowę na liście

#### Scenario: Usunięcie rozmowy otwartej w panelu

- **WHEN** operator usuwa rozmowę, której transkrypt jest właśnie na ekranie
- **THEN** panel przestaje pokazywać ten transkrypt

### Requirement: Panel mówi, że wykres zmienił agent

Terminal MUST czytać nowe polecenia agenta **po zakończonej turze** oraz **po wejściu na
stronę** — pierwsze po to, żeby zmiana była widoczna od razu, drugie po to, żeby polecenie
wydane przed zamknięciem karty nie przepadło.

Zastosowanie polecenia MUST być widoczne dla operatora: panel MUST powiedzieć, że wykres
został zmieniony przez agenta, i czego zmiana dotyczyła. Wykres zmieniający się sam, bez
zdania o tym, czyta się jak usterka.

Panel MUST powiedzieć także o obiektach naniesionych i skasowanych przez agenta
(`agent-chart-drawings`), tą samą drogą i w tej samej chwili co o poleceniu wykresu.
Rysunek, który pojawił się na wykresie bez zdania o tym, jest zmianą, której operator nie
umie przypisać do niczyjej ręki.

Panel MUST wysyłać w żądaniu tury migawkę tego, co rysuje aktywny slot, żeby model mówił
o widocznym wykresie.

Nieudany odczyt poleceń MUST NOT przerywać rozmowy ani czyścić wykresu: panel MUST
pokazywać rozmowę dalej, a polecenie zostanie zastosowane przy następnym udanym odczycie.
To samo MUST dotyczyć nieudanego odczytu naniesionych obiektów.

#### Scenario: Agent zmienia wykres w trakcie rozmowy

- **WHEN** agent kończy turę, w której ustawił wskaźniki
- **THEN** wykres pokazuje je bez odświeżania strony
- **AND** panel mówi, że to agent je ustawił

#### Scenario: Agent nanosi opór w trakcie rozmowy

- **WHEN** agent kończy turę, w której naniósł opór
- **THEN** wykres pokazuje go bez odświeżania strony
- **AND** panel mówi, że to agent go naniósł

#### Scenario: Polecenie wydane przed zamknięciem karty

- **WHEN** operator wraca do terminala po tym, jak agent ustawił wykres w poprzedniej sesji przeglądarki
- **THEN** polecenie zostaje zastosowane raz, przy wejściu na stronę

#### Scenario: Odczyt poleceń zawiódł

- **WHEN** odczyt poleceń agenta się nie powiódł
- **THEN** rozmowa i wykres zostają takie, jakie były

### Requirement: Operator zatrzymuje odpowiedź z panelu

Panel MUST dawać sposób zatrzymania odpowiedzi, dopóki ona trwa, i MUST go pokazywać w tym
samym miejscu, w którym w czasie tury i tak nie da się wysłać następnego pytania. Operator,
który po dwóch zdaniach widzi, że agent odpowiada nie na to pytanie, MUST mieć hamulec
bliżej niż zamknięcie panelu.

Zatrzymanie MUST być żądaniem skierowanym do modułu, a nie samym porzuceniem strumienia
przez terminal: porzucone łącze zostawia turę biegnącą dalej, a operator, który kliknął
zatrzymanie, MUST dostać turę zakończoną.

Po zatrzymaniu panel MUST wrócić do stanu, w którym można pisać dalej, a to, co dotarło,
MUST zostać na ekranie. Zatrzymanie MUST NOT wymagać przeładowania terminala ani otwarcia
rozmowy na nowo.

Zatrzymanie, którego moduł nie przyjął, MUST być powiedziane wprost, a panel MUST NOT
pokazać tury jako zatrzymanej, dopóki moduł tego nie potwierdzi — odpowiedź, która płynie
dalej pod napisem „zatrzymano", jest gorsza niż brak przycisku.

#### Scenario: Operator zatrzymuje trwającą odpowiedź

- **WHEN** odpowiedź agenta płynie, a operator wybiera zatrzymanie
- **THEN** panel żąda zatrzymania od modułu
- **AND** po zakończeniu tury pokazuje to, co dotarło, jako odpowiedź zatrzymaną
- **AND** pozwala napisać następną wiadomość

#### Scenario: Nie ma czego zatrzymywać

- **WHEN** żadna tura nie trwa
- **THEN** panel MUST NOT pokazywać sposobu zatrzymania

#### Scenario: Moduł nie przyjął zatrzymania

- **WHEN** żądanie zatrzymania kończy się błędem
- **THEN** panel mówi to wprost
- **AND** MUST NOT oznaczyć odpowiedzi jako zatrzymanej

#### Scenario: Powrót do zatrzymanej rozmowy

- **WHEN** operator otwiera sesję, w której tura została zatrzymana
- **THEN** panel pokazuje tę wypowiedź jako zatrzymaną, tak samo jak pokazywał ją w chwili
  zatrzymania

### Requirement: Operator ustawia szerokość panelu

Panel rozwinięty MUST dać się rozszerzać i zwężać ciągnięciem za jego krawędź. Szerokość,
którą operator ustawi, MUST być zabrana albo oddana treści zakładki obok — panel odsuwa
ją i wpuszcza z powrotem, a MUST NOT jej zakrywać.

Szerokość MUST przetrwać przeładowanie terminala, tak samo jak stan zwinięcia. Panel
zwinięty i rozwinięty z powrotem MUST wrócić do szerokości, którą operator ustawił, a nie
do domyślnej.

Szerokość MUST być ograniczona z obu stron. Panel MUST NOT dać się zwęzić poniżej miary, w
której przestaje być czytelny, ani rozszerzyć tak, by treść zakładki zniknęła — obie
skrajności zostawiają operatora bez drogi powrotnej inaczej niż przez wyczyszczenie
pamięci przeglądarki. Szerokość zapamiętana wcześniej, a niemieszcząca się w oknie, którym
terminal został właśnie otwarty, MUST zostać sprowadzona do granicy, a nie odtworzona
dosłownie.

Chwyt MUST dać się obsłużyć klawiaturą i MUST nieść dostępną nazwę mówiącą, co robi.

#### Scenario: Operator poszerza panel

- **WHEN** operator ciągnie krawędź panelu w lewo
- **THEN** panel staje się szerszy
- **AND** treść zakładki obok dostaje odpowiednio mniej miejsca, pozostając widoczna

#### Scenario: Szerokość przeżywa przeładowanie

- **WHEN** operator ustawia szerokość panelu i przeładowuje terminal
- **THEN** panel ma tę samą szerokość

#### Scenario: Zwinięcie i rozwinięcie nie gubi miary

- **WHEN** operator zwija panel i rozwija go z powrotem
- **THEN** panel wraca do szerokości, którą operator ustawił

#### Scenario: Ciągnięcie poza granicę

- **WHEN** operator ciągnie krawędź poza dopuszczalną szerokość
- **THEN** panel zatrzymuje się na granicy
- **AND** treść zakładki obok pozostaje widoczna

#### Scenario: Okno węższe niż zapamiętana szerokość

- **WHEN** terminal zostaje otwarty w oknie węższym, niż pozwala zapamiętana szerokość
  panelu
- **THEN** panel dostaje szerokość sprowadzoną do granicy dla tego okna

#### Scenario: Chwyt z klawiatury

- **WHEN** operator ustawia fokus na chwycie i używa klawiszy strzałek
- **THEN** szerokość panelu zmienia się krok po kroku

