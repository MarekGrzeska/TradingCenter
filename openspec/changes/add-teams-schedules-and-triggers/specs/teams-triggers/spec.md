## Purpose

Kiedy zespół rusza dlatego, że coś się stało na rynku, a nie dlatego, że wybiła godzina:
skąd moduł bierze wartość warunku, co znaczy „warunek się spełnił", i czego obserwowanie
rynku nie wolno mu kosztować.

## ADDED Requirements

### Requirement: Warunek jest czytany narzędziami serwera narzędzi

Wartość, na której opiera się warunek, MUST pochodzić z serwera narzędzi, tą samą drogą,
którą czyta rynek agent w przebiegu. Moduł MUST NOT liczyć własnych wskaźników ani sięgać po
archiwum inną drogą niż ta.

Wskaźniki są cudzą własnością i cudzym katalogiem. Drugie ich wyliczenie tutaj znaczyłoby dwie
odpowiedzi na to samo pytanie, rozjeżdżające się przy pierwszej poprawce po tamtej stronie —
a wyzwalacz reagujący na inną wartość niż ta, którą zobaczy uruchomiony zespół, jest gorszy
niż brak wyzwalacza.

#### Scenario: Warunek nazywa wielkość spoza katalogu narzędzi

- **WHEN** operator zapisuje wyzwalacz opisany wielkością, której serwer narzędzi nie ogłasza
- **THEN** zapis zostaje odrzucony z powodem nazywającym tę wielkość

### Requirement: Obserwowanie rynku nie kosztuje tokenów modelu

Sprawdzenie warunku MUST NOT wywołać modelu. Koszt sprawdzenia warunku MUST NOT pojawić się
w zużyciu zespołu, dopóki nie doszło do uruchomienia przebiegu.

Inaczej „obserwuj rynek co pięć minut" kosztowałoby tyle, co „pracuj co pięć minut", a to jest
dokładnie ta różnica, dla której wyzwalacz w ogóle powstaje.

#### Scenario: Warunek sprawdzany wielokrotnie bez spełnienia

- **WHEN** wyzwalacz sprawdza warunek wiele razy i za każdym razem jest on niespełniony
- **THEN** nie powstaje żaden wiersz zużycia tokenów
- **AND** dobowa granica kosztu zespołu nie zostaje naruszona

### Requirement: Wyzwalacz reaguje na zbocze, nie na stan

Wyzwalacz MUST uruchomić przebieg w chwili, w której warunek przeszedł ze stanu niespełnionego
w spełniony. Warunek pozostający spełniony przy kolejnych sprawdzeniach MUST NOT uruchamiać
kolejnych przebiegów. Po wyzwoleniu MUST obowiązywać czas martwy, w którym wyzwalacz nie
wyzwala ponownie.

Warunek typu „cena powyżej poziomu" bywa prawdziwy przez godzinę. Reagowanie na stan zamiast
na przejście dałoby dwanaście przebiegów zamiast jednego, wszystkie z tą samą odpowiedzią.

#### Scenario: Warunek spełniony i pozostający spełniony

- **WHEN** warunek przechodzi w spełniony i pozostaje taki przy kolejnych sprawdzeniach
- **THEN** rusza dokładnie jeden przebieg

#### Scenario: Warunek migający wokół progu

- **WHEN** warunek przestaje być spełniony i spełnia się ponownie, zanim minie czas martwy
- **THEN** kolejny przebieg nie rusza
- **AND** w historii wyzwoleń jest wpis nazywający czas martwy jako powód

### Requirement: Niedostępność serwera narzędzi to nie jest niespełniony warunek

Gdy serwer narzędzi nie odpowiada lub nie jest skonfigurowany, wyzwalacz MUST NOT potraktować
tego jako warunku niespełnionego i MUST NOT uruchomić przebiegu. Sprawdzenie MUST zostać
zapisane jako niedostępność. Odmowa narzędzia MUST być zapisana odrębnie od niedostępności.

Warunek nieznany i warunek fałszywy wyglądają tak samo tylko z zewnątrz. Zapisane jako to samo
dałyby harmonogram, który po cichu nie działa, i operatora przekonanego, że rynek jest spokojny.

#### Scenario: Serwer narzędzi nie odpowiada

- **WHEN** sprawdzenie warunku nie może uzyskać wartości, bo serwer narzędzi jest nieosiągalny
- **THEN** przebieg nie rusza
- **AND** w historii wyzwoleń jest wpis nazywający niedostępność

#### Scenario: Moduł bez skonfigurowanego serwera narzędzi

- **WHEN** operator zapisuje wyzwalacz, a moduł nie ma skonfigurowanego serwera narzędzi
- **THEN** zapis zostaje odrzucony z powodem nazywającym brak serwera narzędzi

### Requirement: Wyzwalacz podlega tym samym granicom co harmonogram

Uruchomienie przebiegu przez wyzwalacz MUST podlegać tym samym zasadom co uruchomienie
z harmonogramu: pominięciu przy trwającym poprzednim przebiegu, wyczerpanej granicy dobowej
zespołu, samoczynnemu wyłączeniu po serii niepowodzeń i wymaganiu jawnego potwierdzenia dla
rewizji z narzędziami zapisującymi.

#### Scenario: Warunek spełnia się przy wyczerpanej granicy dobowej

- **WHEN** warunek przechodzi w spełniony, a zespół wydał już dobową granicę kosztu
- **THEN** przebieg nie rusza
- **AND** w historii wyzwoleń jest wpis nazywający granicę jako powód
