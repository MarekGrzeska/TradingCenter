## Purpose

Zakładka terminala pokazująca zebrane posty: co operator widzi po jej otwarciu, jak oddzielone są
posty ważne od reszty i co ekran mówi, gdy archiwum stoi albo model nie jest skonfigurowany.

## ADDED Requirements

### Requirement: Zakładka pokazuje ostatnią dobę i nazywa okno

Zakładka MUST pokazywać posty z ostatnich 24 godzin, najnowsze najpierw, i MUST nazywać okno oraz
liczbę postów wprost. Operator MUST NOT musieć wnioskować z listy, jak daleko ona sięga.

#### Scenario: Otwarcie zakładki

- **WHEN** operator otwiera zakładkę
- **THEN** widzi posty z ostatniej doby, najnowsze na górze
- **AND** widzi, ilu postów dotyczy lista i jakiego okna

### Requirement: Wysoki wpływ jest widoczny bez klikania, reszta jest zwinięta

Posty z oceną wpływu nie niższą niż próg MUST być widoczne od razu. Pozostałe — o niższej ocenie
oraz nieocenione — MUST być dostępne pod jednym rozwinięciem, które MUST podawać, ile ich jest.

Ekran ma odpowiadać na pytanie „czy stało się coś, co rusza rynkiem", a nie „co dziś napisano".

#### Scenario: Doba z jednym ważnym postem

- **WHEN** w oknie jest jeden post z oceną powyżej progu i czterdzieści innych
- **THEN** ten jeden MUST być widoczny bez rozwijania czegokolwiek
- **AND** pozostałe MUST być dostępne pod rozwinięciem podającym ich liczbę

#### Scenario: Doba bez ważnych postów

- **WHEN** żaden post w oknie nie przekracza progu
- **THEN** ekran MUST to powiedzieć wprost, zamiast wyglądać na pusty

### Requirement: Post pokazuje polski tekst, gdy jest, i oryginał, gdy go nie ma

Karta posta MUST pokazywać tłumaczenie, jeśli istnieje, a w przeciwnym razie treść oryginalną —
i MUST NOT udawać, że tłumaczenie jest, gdy go nie ma. Karta MUST nieść czas publikacji, ocenę
wpływu, jeśli istnieje, tematy oraz drogę do posta u źródła.

#### Scenario: Post bez tłumaczenia

- **WHEN** post nie został przetłumaczony
- **THEN** karta MUST pokazać treść oryginalną

#### Scenario: Post bez oceny

- **WHEN** post nie został oceniony
- **THEN** karta MUST NOT pokazywać oceny zerowej ani żadnej zastępczej

### Requirement: Ekran mówi, gdy archiwum stoi albo model milczy

Zakładka MUST odróżniać trzy stany i nazywać je operatorowi: brak postów w oknie, archiwum
nieświeże, oraz moduł działający bez skonfigurowanego modelu. Pusta lista MUST NOT być jedyną
odpowiedzią na wszystkie trzy.

#### Scenario: Zbiór stanął

- **WHEN** ostatni udany zbiór jest znacznie starszy niż odstęp zbioru
- **THEN** ekran MUST powiedzieć, że archiwum jest nieświeże, wraz z momentem ostatniego zbioru

#### Scenario: Wdrożenie bez modelu

- **WHEN** moduł działa bez skonfigurowanego dostępu do modelu
- **THEN** ekran MUST powiedzieć, że oceny i tłumaczenia nie powstają, zamiast pokazywać same
  posty bez wyjaśnienia

### Requirement: Lista odświeża się sama

Zakładka MUST odświeżać listę bez czynności operatora. Nieudane odświeżenie MUST NOT skasować tego,
co jest już na ekranie — operator patrzący na post MUST NOT stracić go przez jedno nieudane
zapytanie.

#### Scenario: Odświeżenie nie dochodzi

- **WHEN** odświeżenie kończy się błędem, a lista jest już wypełniona
- **THEN** poprzednie posty MUST zostać na ekranie
