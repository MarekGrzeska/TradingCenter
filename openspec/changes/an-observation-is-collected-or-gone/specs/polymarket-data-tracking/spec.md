## ADDED Requirements

### Requirement: Usunięcie obserwacji zabiera wszystko i jest jedynym wyjściem z listy

Moduł MUST pozwalać usunąć obserwację w całości: wydarzenie, jego rynki, jego wyniki, każdą
zebraną próbkę i każdy zapis zebranego zakresu. Usunięcie MUST być niepodzielne — albo znika
wszystko, albo nie znika nic.

Usunięcie MUST być jedynym sposobem, w jaki wydarzenie schodzi z listy obserwacji. Moduł MUST NOT
udostępniać zatrzymania zbierania bez usunięcia: obserwacja, która nie zbiera i nie znika, jest
miejscem na liście, o którym nikt nie umie powiedzieć, po co tam jest.

Ponowne objęcie obserwacją usuniętego wydarzenia MUST zacząć od pustego archiwum. Jest to różnica
warta powiedzenia wprost, bo do niedawna zachodziła odwrotna: zakończona obserwacja podjęta na
nowo zachowywała historię. Po usunięciu nie ma czego zachować, i to jest cała treść tej czynności.

Usunięcie MUST być osiągalne wyłącznie przez kontrakt REST i MUST NOT być osiągalne narzędziem.

#### Scenario: Usunięcie obserwacji

- **WHEN** obserwacja wydarzenia zostaje usunięta
- **THEN** wydarzenie nie występuje już na liście obserwacji
- **AND** nie pozostaje po nim żadna zebrana próbka ani żaden zapis zebranego zakresu
- **AND** moduł przestaje je próbkować

#### Scenario: Ponowne objęcie obserwacją po usunięciu

- **WHEN** usunięte wydarzenie zostaje objęte obserwacją ponownie
- **THEN** obserwacja rusza z pustym archiwum
- **AND** moduł MUST NOT twierdzić, że jakikolwiek okres tego wydarzenia jest już zebrany

#### Scenario: Próba zatrzymania obserwacji bez usunięcia

- **WHEN** konsument szuka sposobu zatrzymania zbierania bez usunięcia obserwacji
- **THEN** moduł żadnego nie udostępnia — ani w kontrakcie, ani w zestawie narzędzi

## REMOVED Requirements

### Requirement: Zakończenie obserwacji zatrzymuje zbieranie i nie rusza danych

**Reason**: zakończenie obserwacji przestaje istnieć jako czynność. Wytwarzało trzeci stan —
wydarzenie, które nie zbiera i nie schodzi z listy — którego nikt nie zamawiał i który wychodził
na jaw dopiero jako wiersz, o który operator pytał „skąd on się tu wziął". Jego miejsce zajmuje
usunięcie obserwacji w całości.

**Migration**: wydarzenia zastane w stanie zakończonym zostają usunięte wraz z zebraną historią
przez migrację modułu. Jest to kasowanie danych, których dostawca w większości przypadków nie
odda, i zostało przyjęte jako świadomy koszt dwóch stanów zamiast trzech. Konsumentom, którzy
zatrzymywali obserwację, pozostaje jej usunięcie; konsumentom, którzy czytali stan `ended`,
pozostają `collecting`, `stalled` i `resolved`.
