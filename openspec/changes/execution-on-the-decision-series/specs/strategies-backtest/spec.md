## MODIFIED Requirements

### Requirement: Decyzja na zamkniętej świecy, wypełnienie od następnej minuty

Silnik MUST liczyć formuły strategii na zamknięciu każdej świecy interwału decyzji, wyłącznie na danych
dostępnych w tej chwili. Zlecenie powstałe w tej decyzji MUST być aktywne najwcześniej od pierwszej minuty po
zamknięciu świecy, a jego wypełnienie MUST być rozstrzygane na serii wykonania instrumentu handlowanego. Seria wykonania
MUST być serią interwału decyzji, gdy dokument nie ma stopu, celu, trailingu ani wejścia zleceniem `limit` lub `stop`.
W każdym innym przypadku MUST być serią `MINUTE`. Na serii decyzji otwarcie pierwszej świecy po decyzji MUST być ceną
pierwszej minuty po decyzji. Świeca jeszcze się formująca MUST NOT brać udziału w żadnej decyzji.

#### Scenario: Zlecenie rynkowe z sygnału

- **WHEN** warunek wejścia jest prawdziwy na świecy H1 zamkniętej o 10:00 UTC
- **THEN** zlecenie rynkowe MUST wypełnić się na otwarciu minuty 10:00–10:01 UTC, z kosztami

#### Scenario: Strategia bez poziomów nie czyta minut

- **WHEN** strategia na `MINUTE_5` wchodzi zleceniem rynkowym, wychodzi tylko przez `when` i biegnie od 1 stycznia
  2026, a archiwum ma świece M5 od 2016 roku i minuty dopiero od 11 sierpnia 2026
- **THEN** uruchomienie MUST NOT czytać serii `MINUTE`
- **AND** wejście z sygnału 2 stycznia MUST wypełnić się na otwarciu następnej świecy M5 tego dnia

#### Scenario: Ta sama strategia na obu seriach

- **WHEN** strategia bez poziomów biegnie na zakresie, w którym pod każdą świecą decyzji są minuty
- **THEN** jej transakcje MUST być co do czasu i ceny wejścia i wyjścia takie same, jak gdyby wykonywała się na
  `MINUTE`

### Requirement: Uruchomienie jest zadaniem w tle z limitami

Żądanie uruchomienia MUST być przyjmowane od razu jako zakolejkowane, z parametrami w zakresach dokumentu.
Wartość poza zakresem MUST być odmową. Uruchomienia MUST wykonywać się w tle, w liczbie nie większej niż
ustawiony limit, i MUST NOT wstrzymywać obsługi innych tras procesu. Zakres przekraczający limit liczby świec
serii wykonania MUST być odrzucony przed startem, a uruchomienie przekraczające limit czasu MUST skończyć się
niepowodzeniem z nazwaną przyczyną. Uruchomienie MUST dać się anulować. Uruchomienie przerwane restartem
procesu MUST zostać oznaczone jako przerwane, a nie pozostać „w toku”.

#### Scenario: Restart w trakcie

- **WHEN** proces restartuje się, gdy uruchomienie jest w toku
- **THEN** po starcie uruchomienie MUST mieć stan niepowodzenia z przyczyną „przerwane restartem”

#### Scenario: Za długi zakres

- **WHEN** zakres wymaga więcej świec serii wykonania, niż pozwala limit
- **THEN** uruchomienie MUST zostać odrzucone przed zakolejkowaniem, z limitem i wymaganą liczbą w komunikacie

#### Scenario: Długi zakres strategii bez poziomów

- **WHEN** strategia bez poziomów na `MINUTE_5` biegnie przez dziesięć lat, czyli więcej minut, niż pozwala limit,
  ale mniej świec M5
- **THEN** uruchomienie MUST zostać zakolejkowane

## ADDED Requirements

### Requirement: Brak minut pod strategią z poziomami jest niepowodzeniem

Gdy seria wykonania to `MINUTE`, a pod którąkolwiek świecą decyzji w zakresie nie ma żadnej minuty, uruchomienie MUST
skończyć się niepowodzeniem, zanim cokolwiek policzy. Przyczyna MUST podawać liczbę takich świec, co najwyżej trzy
pierwsze luki i pierwszą minutę, jaką archiwum ma w zakresie. Silnik MUST NOT przenosić zlecenia ani wyjścia przez
świecę decyzji bez minut. Uruchomienie z serią wykonania równą serii decyzji MUST NOT podlegać temu sprawdzeniu.

#### Scenario: Strategia ze stopem przed początkiem minut

- **WHEN** strategia na `MINUTE_5` ze stopem biegnie od 1 stycznia 2026, a pierwsza ciągła minuta US100 w archiwum jest
  z 11 sierpnia 2026
- **THEN** uruchomienie MUST skończyć się niepowodzeniem bez żadnej transakcji
- **AND** przyczyna MUST nazywać liczbę świec M5 bez minut i pierwszą minutę w archiwum

#### Scenario: Pojedyncza brakująca minuta

- **WHEN** pod świecą M5 brakuje jednej minuty z pięciu
- **THEN** uruchomienie MUST NOT skończyć się niepowodzeniem z tego powodu
