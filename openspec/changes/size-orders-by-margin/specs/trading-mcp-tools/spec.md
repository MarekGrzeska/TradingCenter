## Purpose

Zestaw narzędzi, które moduł publikuje klientowi MCP: co da się nimi przeczytać o rachunku, co
da się nimi na nim zmienić, czego w zestawie nie ma i po czym poznać, że narzędzie odmówiło,
a nie że nie dało się go zapytać.

## ADDED Requirements

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
