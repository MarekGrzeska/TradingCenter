## MODIFIED Requirements

### Requirement: Agent zapisuje w widoku terminala i na rachunku demonstracyjnym

Zmianami stanu, jakie moduł MUST umieć wykonać przez narzędzie, są:
- ustawienie tego, co terminal rysuje: zestawu wskaźników, symbolu i interwału aktywnego slotu;
- postawienie i skasowanie rysunków na wykresie instrumentu (`agent-chart-drawings`);
- zmiana listy obserwacji Polymarket i jej grup w granicach `polymarket-data-tools`;
- zapis rewizji strategii i zakolejkowanie backtestu (`strategies-tools`);
- zmiana stanu rachunku demonstracyjnego: złożenie zlecenia, zamknięcie pozycji, zmiana poziomów zabezpieczających i
  anulowanie zlecenia oczekującego.

Moduł MUST NOT wykonywać przez narzędzia żadnej innej zmiany stanu: nie rozpoczyna zbierania pary, nie kasuje danych,
nie zmienia konfiguracji żadnego modułu, w tym profilu kosztów strategii, i nie pisze do archiwum.

Zapis w widoku terminala MUST być odwracalny ręką operatora, bez rozmowy i bez modelu. Zawartość slotu cofa się tym
samym wybierakiem, którym operator ustawia wykres sam, a rysunek listą, z której operator go usuwa. Narzędzie zmieniające
widok, którego skutku operator nie umie cofnąć bez agenta, jest poza tym wymaganiem.

Rewizja strategii zapisana przez agenta MUST być odwracalna ręką operatora w zakładce Strategies: przywrócenie
wcześniejszej rewizji zapisuje jej treść jako kolejną rewizję. Zakolejkowany backtest MUST dać się tam anulować.
Zakończonego backtestu cofnąć się nie da i MUST NOT dać się go usunąć, bo licznik prób przestałby mówić prawdę. Na miejscu
odwracalności stoją trzy rzeczy: uruchomienie jest zapisane jako zlecone przez agenta, liczy się do licznika prób, a
naraz czeka najwyżej jedno uruchomienie zlecone przez agenta.

Zapis na rachunku MUST NOT być objęty warunkiem odwracalności, bo objąć się nie da: zlecenia wykonanego nikt nie cofa
wybierakiem, a terminal nie ma dziś ekranu pozycji, więc jedyną drogą wewnątrz tej platformy jest poprosić agenta jeszcze
raz. Na miejscu odwracalności stoją trzy rzeczy i żadna z nich nie jest liczbą wpisaną w ten moduł:
- rachunek demonstracyjny wymuszony u gatewaya (`capital-trading`, „Handel dotyka wyłącznie konta demo”);
- imienna lista wołających u serwera narzędzi zapisujących (`trading-mcp-transport`);
- ślad każdego wywołania ruszającego rachunek (`agent-trading`).

#### Scenario: Operator prosi o pokazanie wskaźnika

- **WHEN** operator prosi agenta, żeby pokazał EMA 200 na wykresie
- **THEN** agent ma narzędzie, którym to robi, i wykres to pokazuje

#### Scenario: Operator prosi o naniesienie oporu

- **WHEN** operator prosi agenta, żeby naniósł opór na wskazanej cenie
- **THEN** agent ma narzędzie, którym to robi, i wykres to pokazuje

#### Scenario: Operator prosi o złożenie zlecenia

- **WHEN** operator prosi agenta, żeby złożył zlecenie na wskazanym instrumencie
- **THEN** agent ma narzędzie, którym to robi, i zlecenie zostaje złożone na rachunku
  demonstracyjnym
- **AND** MUST NOT odpowiedzieć, że jest to poza jego zakresem

#### Scenario: Operator prosi o wykonanie akcji poza wykresem

- **WHEN** operator prosi agenta, żeby zaczął zbierać parę albo skasował dane z archiwum
- **THEN** agent nie ma narzędzia, którym mógłby to zrobić
- **AND** odpowiada, że to jest poza jego zakresem, zamiast zgłaszać chwilową awarię

#### Scenario: Operator cofa to, co ustawił agent

- **WHEN** operator usuwa wybierakiem wskaźnik, który ustawił agent
- **THEN** wskaźnik znika i nie wraca sam z siebie

#### Scenario: Operator cofa to, co narysował agent

- **WHEN** operator usuwa z listy rysunek, który postawił agent
- **THEN** rysunek znika i nie wraca sam z siebie

#### Scenario: Operator prosi o zapisanie strategii

- **WHEN** operator opisuje strategię i prosi agenta o jej zapisanie
- **THEN** agent ma narzędzie, którym to robi, i powstaje rewizja z autorem `agent`

#### Scenario: Agent proszony o zmianę kosztów strategii

- **WHEN** operator prosi agenta, żeby zmienił spread w profilu kosztów instrumentu
- **THEN** agent nie ma narzędzia, którym mógłby to zrobić, i mówi, że koszty ustawia operator w zakładce Strategies
