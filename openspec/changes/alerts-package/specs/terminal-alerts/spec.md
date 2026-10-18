## Purpose

Zakładka Alerty w terminalu: reguły, ich historia i kreator, w którym operator niczego nie wpisuje z
pamięci. Do tego pole na zdanie, które wypełnia kreator za operatora.

## ADDED Requirements

### Requirement: Lista reguł mówi, co każda reguła ostatnio zrobiła

Zakładka MUST pokazywać każdą regułę z nazwą, źródłem w słowach, adresatem, stanem (włączona,
wyłączona i z jakiego powodu), ostatnim sprawdzeniem albo zdarzeniem oraz ostatnim odpaleniem z jego
wynikiem. Reguła z wadą MUST być wyróżniona, a liczba takich reguł MUST być widoczna bez przewijania.

#### Scenario: Reguła stanu, której narzędzie nie odpowiada

- **WHEN** ostatnie sprawdzenia reguły skończyły się niedostępnością
- **THEN** wiersz reguły MUST to mówić z powodem, zamiast pokazywać ją jako spokojną

### Requirement: Kreator nie ma pola na nazwę z pamięci

Kreator MUST dawać wybór, a nie pole tekstowe, dla: źródła, typu zdarzenia, atrybutu, narzędzia,
instrumentu, pola wyniku, porównania i adresata. Wartości wybiera się z katalogu pakietu. Pola
filtra MUST powstawać ze schematu typu zdarzenia albo argumentów narzędzia. Wpisywane są wyłącznie
liczby, nazwa reguły i szablon. Odmowa zapisu MUST być pokazana przy polu, którego dotyczy.

#### Scenario: Reguła na kanał YouTube

- **WHEN** operator wybiera typ „film odczytany”
- **THEN** kreator MUST pokazać listę kanałów z archiwum do wyboru i pole oceny jako liczbę, bez pola na nazwę kanału

### Requirement: Szablon ma podgląd

Kreator MUST pokazywać podgląd treści wiadomości wypełnionej przykładowym zdarzeniem tego typu albo
ostatnią wartością warunku, zanim reguła zostanie zapisana.

#### Scenario: Szablon z atrybutem

- **WHEN** operator wpisuje szablon odwołujący się do kanału i oceny
- **THEN** podgląd MUST pokazać te pola wypełnione wartościami przykładu

### Requirement: Zdanie wypełnia kreator, nie zapisuje

Zakładka MUST mieć pole na zdanie. Wynik szkicu MUST otwierać kreator wypełniony szkicem, z wadami
szkicu pokazanymi przy polach. Reguła MUST powstać dopiero po zatwierdzeniu kreatora przez operatora.
Gdy szkice są niedostępne, pole MUST mówić dlaczego.

#### Scenario: Szkic z wadą

- **WHEN** szkic wraca z instrumentem, którego archiwum nie śledzi
- **THEN** kreator MUST otworzyć się wypełniony, z wadą przy polu instrumentu, a zapis MUST być niedostępny, dopóki wada nie zniknie

### Requirement: Historia odpaleń jest czytelna bez bazy

Dla każdej reguły zakładka MUST pokazywać ostatnie odpalenia z czasem, źródłem, treścią i wynikiem,
w tym pominięcia z powodu czasu martwego, zdławienia, niedostępności i odpuszczenia.

#### Scenario: Reguła zdławiona

- **WHEN** reguła została zdławiona sufitem wysyłek
- **THEN** historia MUST pokazywać zdławione odpalenia z tym powodem
