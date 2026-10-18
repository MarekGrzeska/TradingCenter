## Context

`destinations` ma dziś `name text UNIQUE` i `bot_id NOT NULL`. Nazwa adresuje wiadomość, więc wskazuje dokładnie jedno
wiązanie i jednego bota. Reguła pakietu `alerts` trzyma tylko `destination` (nazwę). Wiązanie powstaje z jednorazowego
tapnięcia `/start` (`binding_nonces.destination_id`), a stan (`pending`/`ready`/`blocked`) i `chat_id` żyją w wierszu.
Powód zmiany: `proposal.md`.

## Goals / Non-Goals

**Goals:**
- Jedna nazwa odbiorcy, kilka botów, bot wybierany przez regułę.
- Istniejące reguły i adresaci działają po wdrożeniu bez przepisywania i bez kroku operatora.
- Dwuznaczność nigdy nie jest rozstrzygana po cichu.

**Non-Goals:**
- Osobna encja „osoba” z listą czatów. Nazwa pozostaje etykietą, którą operator sam nadaje.
- Ominięcie tapnięcia `/start` przy drugim bocie. Telegram nie pozwala botowi napisać pierwszemu, a czat prywatny
  jednego bota nie jest dowodem, że drugi bot ma prawo pisać.

## Decisions

**1. Zostaje jedna tabela; unikalna jest para (nazwa, bot).** Unikalność `name` zastępuje `UNIQUE (name, bot_id)`.
Czat, stan, blokada i tapnięcie zostają per wiersz, więc `binding`, `bind_destination`, `mark_blocked` i
`binding_nonces` nie zmieniają się w ogóle. Zablokowanie jednego bota nie rusza wiązania przez drugiego — to jest wprost
zachowanie, o które chodzi.
*Alternatywa: osobna tabela `recipients` (osoba) i `destinations` jako wiązanie (osoba, bot).* Czystsza, ale dotyka
każdej trasy, tokenu startowego, migracji nazw i wszystkich reguł (nazwa → klucz obcy w innej bazie). Za dużo, żeby
dostać jedyną rzecz, której operator potrzebuje: wybrać bota. Jeśli kiedyś potrzebne będą grupy lub wiele osób, nazwa z
tej decyzji migruje do tabeli bez zmiany kontraktu.

**2. Bot w kontrakcie to `@username`, pomijalny tylko przy jednym wiązaniu.** `POST /messages {destination, bot?}`:
z botem — dokładnie to wiązanie; bez bota — gdy nazwa ma jedno wiązanie, to ono, a gdy ma kilka, odmowa `409` z listą
botów. `DELETE /destinations/{name}?bot=…` działa tak samo: bez `bot` usuwa tylko przy jednym wiązaniu.
*Alternatywa: pierwszy lub „najstarszy” bot.* Odrzucona: wiadomość trafiłaby innym botem, niż operator myślał, i nikt by
tego nie zauważył. Dotychczasowe wymaganie „kontrakt nie przyjmuje nazwy bota” istniało po to, żeby wymiana bota nie
unieważniała kopii identyfikatorów u wywołujących; tu jest odwrotnie z wyboru — bot jest częścią decyzji reguły i
wymiana bota ma unieważnić dokładnie reguły, które go wskazują, głośno, jako ich wadę.

**3. Reguła dostaje `bot text NULL`.** Pusty bot to „jedyny bot tego adresata” — czyli dokładnie dotychczasowe
znaczenie każdej istniejącej reguły. Kolumna jest dodawana bez wartości i bez konwersji, więc nie ma migracji danych
między bazami (baza `alerts` nie czyta bazy `telegram`).
*Alternatywa: wypełnić `bot` przy starcie z listy adresatów bramy.* Odrzucona: kolejna jednorazowa konwersja z oknem,
w którym brama nie odpowiada, a zysk jest żaden — pusty bot opisuje to samo, dopóki adresat ma jedno wiązanie.

**4. Dwuznaczność jest wadą reguły.** Reguła z pustym botem i adresatem o kilku wiązaniach ma wadę przy polu `bot`
(„adresat dociera przez kilku botów; wskaż którego”) i nie doręcza: odpalenie kończy się odmową z tym powodem, a
`/state` liczy ją do `rules_with_defects`. Reguła z botem, którego adresat nie ma (usunięty bot, usunięte wiązanie),
ma wadę „adresat nie dociera przez tego bota”. Zapis odrzuca obie, jak dziś odrzuca nieznanego adresata. Przy
niedostępnej bramie nie ma kogo pytać, więc zapis nie sprawdza i mówi to wprost.

**5. Katalog dla formularza zwraca wiązania, nie nazwy.** `GET /catalog` już zwraca listę `recipients: [{name, bot,
receives}]`, czyli wiązania. Formularz grupuje ją sam i pokazuje w „Którym botem” tylko boty wybranego adresata,
odbierających jako domyślnych. Nie ma nowej trasy.

## Risks / Trade-offs

- [Reguła bez bota przestaje działać, gdy operator doda adresatowi drugiego bota] → to ma być głośne: wada reguły,
  licznik w `/state`, ostrzeżenie w oknie dodawania drugiego bota („reguły bez wskazanego bota przestaną doręczać”).
  Alternatywą byłaby cicha zmiana adresu, gorsza.
- [Dwie reguły o tej samej nazwie i różnych botach wyglądają na liście jednakowo] → wiersz reguły mówi „adresat
  przez @bot”.
- [`DELETE /destinations/{name}` bez `bot` odmawia przy kilku wiązaniach] → terminal zawsze wysyła bota.
- [Ten sam czat prywatny związany przez dwa boty to dwa wiersze z tym samym `chat_id`] → unikalność `(bot_id, chat_id)`
  zostaje, więc to nie koliduje.

## Migration Plan

1. Migracja `telegram`: zdjęcie unikalności `name`, `ADD CONSTRAINT UNIQUE (name, bot_id)`. Addytywna: istniejące
   wiersze ją spełniają, bo nazwa była unikalna.
2. Migracja `alerts`: `ALTER TABLE rules ADD COLUMN bot text`. Addytywna.
3. Wdrożenie jedno, obie migracje pod własnymi blokadami (jak dziś). Wycofanie obrazu zostawia indeks i kolumnę
   nieszkodliwe dla starego kodu, o ile żadnemu adresatowi nie dodano jeszcze drugiego bota; po dodaniu drugiego stary
   obraz widzi dwa wiersze pod jedną nazwą i `destination_by_name` zwraca pierwszy. Dlatego pierwszy dodany drugi bot jest
   ruchem po zweryfikowanym wdrożeniu, nie częścią niego.

## Open Questions

Brak.
