## Context

`destinations` ma dziś `name text UNIQUE` i `bot_id NOT NULL`: jeden wiersz to jednocześnie „kto” (nazwa) i „przez kogo”
(bot, czat, stan). Nazwa adresuje wiadomość, więc wskazuje dokładnie jedno wiązanie. Reguła pakietu `alerts` trzyma tylko
`destination` (nazwę). Wiązanie powstaje z jednorazowego tapnięcia `/start` (`binding_nonces.destination_id`), a stan
(`pending`/`ready`/`blocked`) i `chat_id` żyją w wierszu. Powód zmiany: `proposal.md`.

Słownik tej zmiany: **adresat** = nazwany odbiorca (wiersz `recipients`); **wiązanie** = adresat × bot z własnym czatem,
stanem i tapnięciem (wiersz `destinations`, który zachowuje nazwę tabeli, bo to ona ma `binding_nonces`, czat, stan i
blokadę).

## Goals / Non-Goals

**Goals:**
- Adresat istnieje raz, niezależnie od botów; do niego dowiązuje się boty, każdy własnym tapnięciem.
- Bot wybierany przez regułę, osobno od adresata.
- Istniejące reguły i adresaci działają po wdrożeniu bez przepisywania i bez kroku operatora.
- Dwuznaczność nigdy nie jest rozstrzygana po cichu.

**Non-Goals:**
- Wiele osób w jednym adresacie i grupy („wyślij do wszystkich moich botów”). Tabela adresatów jest właściwym miejscem,
  ale to osobna zmiana.
- Ominięcie tapnięcia `/start` przy kolejnym bocie. Telegram nie pozwala botowi napisać pierwszemu.

## Decisions

**1. Osobna tabela `recipients`; `destinations` staje się wiązaniem.** `recipients(id, name UNIQUE, created_at)`.
`destinations` dostaje `recipient_id NOT NULL REFERENCES recipients(id) ON DELETE CASCADE` i `UNIQUE (recipient_id,
bot_id)`; czat, stan, blokada, tożsamość czatu i `binding_nonces` zostają przy wiązaniu. Adresat może istnieć bez
żadnego wiązania (zamiar przed pierwszym tapnięciem).
*Alternatywa: jedna tabela z `UNIQUE (name, bot_id)`.* Mniejsza, ale „kto” nadal jest tylko etykietą powtarzaną w
wierszach: zmiana nazwy to update wielu wierszy, usunięcie adresata to usunięcie wielu wierszy po tekście, a grupy i
wiele osób nie mają gdzie zamieszkać. Operator wybrał osobną tabelę.

**2. Kontrakt: adresat i wiązanie to dwa zasoby.** `GET/POST /recipients`, `DELETE /recipients/{name}` (adresat ze
wszystkimi wiązaniami), `POST /recipients/{name}/bots` (`{bot}` → odnośnik startowy, powtórzenie wydaje nowy sekret),
`DELETE /recipients/{name}/bots/{bot}` (jedno wiązanie). `GET /recipients` zwraca adresata z listą wiązań, a każde ma bota,
stan i `receives`. Dotychczasowe trasy `/destinations` znikają: wołają je terminal i pakiet `alerts`, oba w tym
repozytorium. `POST /messages` przyjmuje `{recipient, bot?, text}`: z botem — dokładnie to wiązanie; bez bota — gdy
adresat ma jedno wiązanie, to ono, a przy kilku odmowa `409` z listą botów.
*Alternatywa: zostawić `/destinations` z innym kształtem.* Odrzucona: ta sama nazwa trasy znaczyłaby inną rzecz niż
tabela i niż słowo w terminalu.

**3. Bot w kontrakcie to `@username`.** Pominięty tylko przy jednym wiązaniu; nigdy „pierwszy” ani „najstarszy”, bo
wiadomość poszłaby innym botem, niż operator myślał, i nikt by tego nie zauważył. Dotychczasowe wymaganie „kontrakt nie
przyjmuje nazwy bota” istniało po to, żeby wymiana bota nie unieważniała kopii identyfikatorów u wywołujących; tu jest
odwrotnie z wyboru — bot jest częścią decyzji reguły, więc jego wymiana ma unieważnić dokładnie reguły, które go
wskazują, głośno, jako ich wadę.

**4. Reguła dostaje `bot text NULL`, a `destination` zostaje nazwą adresata.** Pusty bot to „jedyne wiązanie tego
adresata” — dokładnie dotychczasowe znaczenie każdej istniejącej reguły. Baza `alerts` nie czyta bazy `telegram`, więc
nie ma konwersji między bazami, tylko jedna nullowalna kolumna.
*Alternatywa: wypełnić `bot` przy starcie z listy wiązań.* Odrzucona: kolejna jednorazowa konwersja z oknem, w którym
brama nie odpowiada, a zysk żaden dopóki adresat ma jedno wiązanie.

**5. Dwuznaczność jest wadą reguły.** Reguła z pustym botem i adresatem o kilku wiązaniach ma wadę przy polu `bot`
(„adresat dociera przez kilku botów; wskaż którego”) i nie doręcza: odpalenie kończy się odmową z tym powodem, a `/state`
liczy ją do `rules_with_defects`. Reguła z botem, przez którego adresat nie jest związany (usunięty bot, usunięte
wiązanie), ma wadę „adresat nie dociera przez tego bota”. Zapis odrzuca obie, jak dziś nieznanego adresata. Przy
niedostępnej bramie nie ma kogo pytać, więc zapis nie sprawdza i mówi to wprost.

**6. Katalog dla formularza zwraca wiązania.** `GET /catalog` już zwraca `recipients: [{name, bot, receives}]`; zostaje
tym samym kształtem (jeden wpis na wiązanie), więc formularz sam grupuje i pokazuje w „Którym botem” boty wybranego
adresata, odbierających jako domyślnych. Pakiet `alerts` czyta ten kształt z bramy przez nową trasę `/recipients`.

## Risks / Trade-offs

- [Wycofanie obrazu po migracji] → kontrakt rozszerz–zawęź: migracja **zostawia** kolumnę `destinations.name` (kopia nazwy, bez
  unikalności i nieczytana przez nowy kod; unikalność musi zejść, inaczej drugie wiązanie tej samej nazwy się nie wstawi), więc stary obraz dalej działa dopóki żaden adresat nie ma dwóch wiązań.
  Usunięcie kolumny `name` jest osobną migracją w następnej zmianie, po jednym zweryfikowanym wydaniu.
- [Reguła bez bota przestaje działać, gdy adresat dostaje drugiego bota] → głośno: wada reguły, licznik w `/state`,
  ostrzeżenie w oknie dodawania drugiego bota. Cicha zmiana adresu byłaby gorsza.
- [Dwie reguły o tym samym adresacie i różnych botach wyglądają na liście jednakowo] → wiersz reguły mówi „przez @bot”.
- [Usunięcie adresata kasuje wszystkie jego wiązania] → okno potwierdzenia wymienia boty; usunięcie jednego bota to
  osobny, mniejszy ruch.
- [Zmiana nazwy adresata] → poza zakresem: reguły trzymają nazwę, więc rename wymagałby ruchu po bazie `alerts`.

## Migration Plan

1. Migracja `telegram` (addytywna): `CREATE TABLE recipients`; `INSERT … SELECT DISTINCT name FROM destinations`;
   `ALTER TABLE destinations ADD COLUMN recipient_id`; backfill po nazwie; `SET NOT NULL`, klucz obcy, `UNIQUE
   (recipient_id, bot_id)`. Unikalność `name` jest zdejmowana, a sama kolumna zostaje do następnej zmiany (kontrakt rozszerz–zawęź).
2. Migracja `alerts`: `ALTER TABLE rules ADD COLUMN bot text`. Addytywna.
3. Wdrożenie jedno, obie migracje pod własnymi blokadami (jak dziś). Pierwszy dodany drugi bot to ruch operatora po
   zweryfikowanym wdrożeniu, nie część niego (patrz ryzyko wycofania).

## Open Questions

Brak.
