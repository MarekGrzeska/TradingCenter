## MODIFIED Requirements

### Requirement: Zestaw dopisuje, ale nie usuwa

Zestaw MUST zawierać narzędzia czytające archiwum oraz narzędzia zapisujące wyłącznie: dopisanie
kanału, dopisanie tematu i wskazanie filmu do analizy, każde z opcjonalnym wyborem istniejącego promptu. Żadne
narzędzie MUST NOT zdejmować obserwacji, kasować filmów ani odczytów, tworzyć, zmieniać ani usuwać promptów,
zmieniać ustawień modułu, ustawiać niczego, co decyduje o powiadomieniach, ani sięgać po cokolwiek związanego z
rachunkiem. Ograniczenie MUST być sprawdzane testem.

#### Scenario: Lista narzędzi

- **WHEN** klient prosi o listę narzędzi
- **THEN** MUST NOT być na niej narzędzia usuwającego cokolwiek, dotykającego rachunku, ustawiającego powiadomienia ani piszącego promptu

### Requirement: Zestaw domyka drogę od pytania do odczytu

Model MUST móc bez wcześniejszej wiedzy: sprawdzić stan archiwum razem z nazwami promptów, odczytać ostatnie filmy
z zawężeniem po kanale, temacie i ocenie, otworzyć odczyty jednego filmu oraz wyszukać filmy frazą. Tekst odczytu
dłuższy niż limit narzędzia MUST zostać skrócony z informacją, że jest skrócony.

#### Scenario: Pytanie o to, co kanały mówią o złocie

- **WHEN** operator pyta, co kanały mówią o złocie w tym tygodniu
- **THEN** model MUST móc odpowiedzieć narzędziami zestawu, czytając odczyty ostatnich filmów, nie znając
  identyfikatora żadnego filmu
