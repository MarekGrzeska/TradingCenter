## ADDED Requirements

### Requirement: Długa treść idzie w częściach

Treść odpalenia dłuższa niż limit jednej wiadomości bramy MUST zostać wysłana jako kolejne wiadomości, każda w tym
limicie, podzielona na granicy akapitu, a gdy akapit się nie mieści — linii, potem słowa. Odpalenie MUST pamiętać,
ile części doręczono, a ponowienie MUST wysłać tylko części niedoręczone. Odpalenie MUST być doręczone dopiero po
ostatniej części. Sufit wysyłek na godzinę MUST liczyć odpalenia, nie części, i MUST NOT zdławić odpalenia, którego
część już doręczono.

Telegram odmawia wiadomości ponad 4096 znaków, a pełny odczyt filmu ma ich kilkanaście tysięcy. Ponowienie od
początku wysłałoby operatorowi pierwsze części drugi raz.

#### Scenario: Treść na trzy wiadomości

- **WHEN** treść odpalenia ma trzy limity jednej wiadomości
- **THEN** pakiet MUST wysłać trzy wiadomości w kolejności treści i oznaczyć odpalenie jako doręczone

#### Scenario: Brama milknie w połowie

- **WHEN** brama przyjmuje pierwszą część, a drugiej nie da się wysłać
- **THEN** odpalenie MUST czekać na ponowienie, a ponowienie MUST zacząć od drugiej części
