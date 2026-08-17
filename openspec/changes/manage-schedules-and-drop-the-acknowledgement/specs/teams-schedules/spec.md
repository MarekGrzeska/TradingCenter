## REMOVED Requirements

### Requirement: Harmonogram nad rewizją z narzędziami zapisującymi wymaga jawnego potwierdzenia

**Reason**: Wymaganie było egzekwowane w jednym miejscu z dwóch i przez to nie dawało
własności, którą obiecuje. Sprawdzenie chodziło wyłącznie przy zapisie harmonogramu;
ścieżka wyzwolenia nie pytała o potwierdzenie ani razu, a przy trybie „najnowsza rewizja"
rewizja jest brana z chwili wyzwolenia. Harmonogram zapisany legalnie nad rewizją z samym
odczytem wyzwalał się więc dalej sam po tym, jak operator dodał do zespołu narzędzie
składające zlecenia — bez potwierdzenia i bez odmowy. Domknięcie tej dziury znaczyłoby
sprawdzanie przy każdym wyzwoleniu, czyli zatrzymywanie harmonogramu w nocy za zgodą, której
nie ma komu wtedy udzielić.

Zatrzymywało za to drogę uczciwą: operator, który prosi o harmonogram w rozmowie, dostawał
odmowę nazywającą pole, którego czat nie umie wypełnić i którego nie da się włączyć nigdzie
indziej, bo jest polem tego harmonogramu. Zabezpieczenie, które przepuszcza drogę cichą i
zatrzymuje głośną, uczy klikania w potwierdzenie, a nie ostrożności.

**Migration**: Nieodwracalne zmiany rachunku zatrzymują trzy rzeczy, które zostają i działają
niezależnie od tego wymagania: rachunek demonstracyjny wymuszony u gatewaya
(`capital-trading`), granice handlowe zapisane w rewizji zespołu (`teams-trading`) oraz ślad
każdego wywołania ruszającego rachunek, powstający przed wysłaniem (`agent-trading`,
`teams-trading`). Harmonogramy zapisane dotąd z potwierdzeniem i bez niego działają tak samo
— znika kolumna, nie znaczenie żadnego wiersza.

## ADDED Requirements

### Requirement: Harmonogram i wyzwalacz dają się usunąć

Moduł MUST pozwalać właścicielowi usunąć harmonogram i wyzwalacz. Usunięcie MUST być
odróżnialne od wyłączenia: wyłączony wpis zostaje w katalogu ze swoim powodem i daje się
włączyć z powrotem, usunięty przestaje istnieć.

Usunięcie MUST zabrać ze sobą historię wyzwoleń tego wpisu i MUST NOT ruszyć przebiegów,
które z niej wystartowały. Historia wskazuje wpis, który ją wytworzył, i bez niego nie ma
jak istnieć; przebieg jest zapisem tego, co się wydarzyło — jego koszt i jego ślad handlowy
przeżywają usunięcie harmonogramu, który go zamówił.

Usunięcie cudzego wpisu MUST być nieodróżnialne od usunięcia nieistniejącego.

#### Scenario: Operator usuwa harmonogram

- **WHEN** właściciel usuwa swój harmonogram
- **THEN** harmonogram znika z katalogu i przestaje się wyzwalać
- **AND** przebiegi, które z niego wystartowały, zostają wraz ze swoim kosztem

#### Scenario: Usunięcie zabiera historię wyzwoleń

- **WHEN** właściciel usuwa harmonogram, który wyzwalał się wcześniej
- **THEN** zapisy jego wyzwoleń znikają razem z nim
- **AND** usunięcie nie zostaje odrzucone z powodu ich istnienia

#### Scenario: Wyłączenie to nie usunięcie

- **WHEN** operator wyłącza harmonogram, zamiast go usunąć
- **THEN** harmonogram zostaje w katalogu ze swoim powodem wyłączenia
- **AND** daje się włączyć z powrotem

#### Scenario: Cudzy harmonogram

- **WHEN** ktoś inny niż właściciel usuwa harmonogram
- **THEN** odpowiedź jest taka sama jak dla harmonogramu, którego nie ma
- **AND** harmonogram zostaje nietknięty
