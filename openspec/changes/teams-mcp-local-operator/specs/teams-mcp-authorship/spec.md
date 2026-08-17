## MODIFIED Requirements

### Requirement: Brak tożsamości operatora zatrzymuje zapis, nie podstawia zastępczej

Gdy tożsamości operatora nie da się ustalić, a **mogła** być ustalona, narzędzie zmieniające
stan MUST odmówić i MUST nazwać ten brak jako powód. MUST NOT wykonać zapisu tożsamością
usługi, tożsamością domyślną ani żadną inną wybraną w zastępstwie. Odczyt MUST być odmówiony
tak samo — bez tożsamości nie ma katalogu, który miałby być czytany.

„Mogła być ustalona" znaczy: przed modułem stoi warstwa uwierzytelniająca **albo** moduł
`teams` jest wołany pod adresem innym niż pętla zwrotna. Wystarczy jedno z dwojga, i wtedy
obowiązuje odmowa opisana wyżej.

Zapis „w czyimś imieniu, nie wiadomo czyim" jest wierszem, którego nikt później nie umie
przypisać ani odwołać — a przy harmonogramie jest to wiersz, który zacznie sam wydawać
pieniądze.

Gdy **żadne** z dwojga nie zachodzi — nikt nie stoi przed modułem i `teams` jest lokalne —
nie istnieje warstwa, która mogłaby wystawić jakikolwiek token, więc odmowa nie chroni już
niczego: zabiera całą powierzchnię narzędzi maszynie deweloperskiej. W tym i tylko w tym
kształcie narzędzie MUST wykonać wywołanie **nie przenosząc żadnej tożsamości**, a właściciel
MUST być tym, którego `teams` przypisuje samo każdemu nieuwierzytelnionemu żądaniu. To nie
jest tożsamość zastępcza wybrana przez ten moduł: moduł nie wybiera niczego, nie wysyła
poświadczenia i nie zna nazwy, która padnie po drugiej stronie.

Moduł MUST powiedzieć przy starcie, w którym z tych dwóch stanów jest — stan, w którym
narzędzia działają bez tożsamości, MUST NOT być stanem, o którym dowiaduje się z braku
odmowy.

#### Scenario: Żądanie zapisujące bez tożsamości za warstwą uwierzytelniającą

- **WHEN** wywołanie narzędzia zapisującego dociera bez ustalonej tożsamości operatora, a
  przed modułem stoi warstwa uwierzytelniająca
- **THEN** MUST zostać odmówione z powodem nazywającym brak tożsamości
- **AND** żaden wiersz MUST NOT powstać

#### Scenario: Odczyt bez tożsamości za warstwą uwierzytelniającą

- **WHEN** wywołanie narzędzia czytającego dociera bez ustalonej tożsamości operatora, a
  przed modułem stoi warstwa uwierzytelniająca
- **THEN** MUST zostać odmówione tak samo — bez tożsamości nie ma katalogu, który miałby być
  czytany

#### Scenario: Zdalny `teams` bez warstwy uwierzytelniającej przed modułem

- **WHEN** wywołanie dociera bez tożsamości operatora, przed modułem nie stoi warstwa
  uwierzytelniająca, ale `teams` jest wołane pod adresem spoza pętli zwrotnej
- **THEN** MUST zostać odmówione
- **AND** powód MUST nazywać brak tożsamości, a nie adres — brakuje tożsamości, adres tylko
  mówi, że mogła istnieć

#### Scenario: Maszyna deweloperska, gdzie nikt nie może być uwierzytelniony

- **WHEN** wywołanie dociera bez tożsamości operatora, przed modułem nie stoi warstwa
  uwierzytelniająca i `teams` jest wołane w pętli zwrotnej
- **THEN** wywołanie MUST zostać wykonane bez przeniesienia jakiejkolwiek tożsamości
- **AND** to, co powstanie, MUST należeć do principala, którego `teams` przypisuje
  nieuwierzytelnionemu żądaniu
- **AND** MUST być widoczne w terminalu na tej samej liście, na której stoi zespół złożony
  ręcznie na tej samej maszynie

#### Scenario: Moduł mówi, w którym stanie wstał

- **WHEN** moduł startuje w kształcie, w którym narzędzia działają bez tożsamości operatora
- **THEN** MUST powiedzieć to przy starcie, nazywając oba warunki, które go do tego stanu
  doprowadziły

#### Scenario: Tożsamość z argumentu narzędzia pozostaje bez znaczenia w każdym stanie

- **WHEN** wywołanie niesie tożsamość w argumencie narzędzia — niezależnie od tego, czy przed
  modułem stoi warstwa uwierzytelniająca
- **THEN** argument MUST zostać zignorowany albo odrzucony
- **AND** MUST NOT powstać nic należącego do tożsamości z argumentu
