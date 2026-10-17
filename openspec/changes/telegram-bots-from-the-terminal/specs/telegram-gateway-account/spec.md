## Purpose

Konto Telegrama, które jest właścicielem botów: jak operator loguje je z terminala, gdzie i w jakiej
postaci leży jego sesja, i jak się ją odbiera — tak, żeby zrzut bazy nie był kluczem do konta.

## ADDED Requirements

### Requirement: Logowanie konta z ekranu, w krokach Telegrama

Brama MUST pozwolić operatorowi zalogować konto-właściciela przez kontrakt REST w krokach, które
narzuca Telegram: numer telefonu, kod, a gdy konto ma hasło dwuetapowe — hasło. Rozpoczęte
logowanie MUST wygasać po 10 minutach i MUST NOT przeżywać restartu procesu; nowe rozpoczęcie
MUST zastępować poprzednie.

#### Scenario: Konto z hasłem dwuetapowym

- **WHEN** operator podaje numer, potem poprawny kod, a konto ma hasło dwuetapowe
- **THEN** brama MUST odpowiedzieć, że czeka na hasło, i MUST NOT uznać logowania za zakończone

#### Scenario: Zły kod

- **WHEN** operator podaje kod, który Telegram odrzuca
- **THEN** brama MUST odmówić słowami Telegrama i MUST pozwolić podać kod ponownie w tym samym logowaniu

#### Scenario: Logowanie przerwane restartem

- **WHEN** proces restartuje się między podaniem numeru a kodu
- **THEN** podanie kodu MUST być odmową mówiącą, że logowanie trzeba zacząć od numeru

### Requirement: Logowanie mówi, dokąd poszedł kod, i pozwala poprosić o inną drogę

Odpowiedź na podanie numeru MUST nazywać, którą drogą Telegram wysłał kod: do aplikacji zalogowanej na koncie, SMS-em
albo telefonem. Brama MUST pozwolić poprosić o następną drogę (aplikacja, potem SMS, potem telefon) w tym samym
logowaniu, tak żeby kod, który przyjdzie, przyjęło to logowanie. Odmowa Telegrama (na przykład brak kolejnej drogi) MUST
dotrzeć jego słowami i MUST zostawić logowanie otwarte.

Kod wysłany do aplikacji, na którą nikt nie patrzy, wygląda jak kod, który nie przyszedł; operator musi wiedzieć, gdzie
szukać, zanim zacznie wysyłać następne prośby, które Telegram ogranicza.

#### Scenario: Kod poszedł do aplikacji

- **WHEN** operator podaje numer konta zalogowanego w aplikacji Telegrama
- **THEN** odpowiedź MUST mówić, że kod poszedł do aplikacji, a zakładka MUST to napisać wprost

#### Scenario: Kod nie przyszedł

- **WHEN** operator prosi o kod jeszcze raz w otwartym logowaniu
- **THEN** brama MUST poprosić Telegram o następną drogę, nazwać ją w odpowiedzi i przyjąć kod z niej w tym samym logowaniu

#### Scenario: Prośba bez logowania

- **WHEN** ktoś prosi o kod jeszcze raz, a żadne logowanie nie jest otwarte
- **THEN** brama MUST odmówić, mówiąc, że trzeba zacząć od numeru

### Requirement: Sesja leży w bazie wyłącznie zaszyfrowana

Po udanym logowaniu brama MUST zapisać sesję konta w swojej bazie wyłącznie w postaci zaszyfrowanej
kluczem z ustawienia `TELEGRAM_SESSION_KEY`. Klucz MUST NOT trafiać do bazy. Bez tego ustawienia
logowanie MUST być odmową nazywającą ustawienie, a wysyłka i wklejanie tokenów MUST działać jak
dotąd.

Zrzut bazy codziennie trafia na komputer operatora; zaszyfrowana sesja w zrzucie bez klucza z
serwera nie otwiera konta.

#### Scenario: Zrzut bazy

- **WHEN** ktoś czyta tabelę z sesją w zrzucie bazy
- **THEN** MUST NOT znaleźć tam sesji w postaci, którą da się użyć bez klucza

#### Scenario: Brak klucza

- **WHEN** `TELEGRAM_SESSION_KEY` nie jest ustawiony, a operator zaczyna logowanie
- **THEN** brama MUST odmówić, nazywając to ustawienie, zanim odezwie się do Telegrama

### Requirement: Sesja, której nie da się użyć, jest stanem, nie awarią

Gdy zapisanej sesji nie da się odszyfrować albo Telegram ją odrzuca, brama MUST nadal startować i
wysyłać, MUST powiedzieć przez trasę stanu, że sesja wymaga ponownego logowania, i MUST odmawiać
zakładania, kasowania i rotacji z tym powodem.

#### Scenario: Klucz zmieniony

- **WHEN** w bazie leży sesja zaszyfrowana innym kluczem niż obecny
- **THEN** brama MUST wstać, a trasa stanu MUST mówić, że konto trzeba zalogować ponownie

#### Scenario: Sesja zabita z telefonu

- **WHEN** operator zakończył sesję w ustawieniach Telegrama, a potem prosi o założenie bota
- **THEN** brama MUST odmówić, mówiąc, że Telegram odrzucił sesję i konto trzeba zalogować ponownie

### Requirement: Wylogowanie odbiera sesję u Telegrama

Wylogowanie MUST unieważnić sesję po stronie Telegrama i MUST usunąć ją z bazy. Gdy Telegram nie
odpowiada, brama MUST usunąć sesję z bazy mimo to i MUST powiedzieć, że unieważnienie u Telegrama
się nie odbyło.

#### Scenario: Telegram nie odpowiada przy wylogowaniu

- **WHEN** operator wylogowuje konto, a Telegram jest nieosiągalny
- **THEN** sesja MUST zniknąć z bazy, a odpowiedź MUST mówić, że trzeba ją zakończyć także w ustawieniach Telegrama

### Requirement: Kod, hasło i sesja nie wychodzą

Żadna odpowiedź, żaden log i żaden komunikat błędu MUST NOT zawierać kodu logowania, hasła
dwuetapowego, sesji ani klucza. Trasa stanu MUST podawać nazwę zalogowanego konta, a numer telefonu
wyłącznie zamaskowany.

#### Scenario: Odczyt stanu po logowaniu

- **WHEN** operator odczytuje stan bramy z zalogowanym kontem
- **THEN** widzi nazwę konta i numer z odsłoniętymi co najwyżej czterema ostatnimi cyframi, bez sesji
