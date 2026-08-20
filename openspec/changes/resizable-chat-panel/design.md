## Context

Panel jest kolumną w rzędzie `flex` shella (`app/Shell.tsx`), a nie warstwą nad treścią —
i to jest już powód, dla którego zakładka oddaje mu miejsce zamiast być przez niego
zakrywana. Sąsiad ma `min-w-0`, z komentarzem mówiącym dlaczego: bez tego wykresy nie
oddają szerokości z powrotem, bo domyślne `min-width: auto` liczy raz zmierzone płótno
jako treść. Szerokość panelu to dziś jedna klasa `w-115` w `AgentChat.tsx`. Stan zwinięcia
mieszka w `agentChatStore` i w `localStorage` pod `terminal.agentChat.v1`.

Motywacja: proposal.md. Wymagania: `specs/terminal-agent-chat` w tej zmianie.

## Goals / Non-Goals

**Goals:**

- Szerokość jako stan panelu, trwały tak samo jak zwinięcie.
- Chwyt dostępny myszą i klawiaturą.

**Non-Goals:**

- Osobna szerokość per zakładka. Panel należy do terminala, nie do zakładki — dwie miary
  dla jednego panelu byłyby sprzeczne z wymaganiem, które już stoi.
- Układ wielopanelowy, przeciąganie panelu na drugą stronę, odczepianie do osobnego okna.
- Zapamiętywanie szerokości po stronie modułu. To jest ustawienie tej przeglądarki, jak
  zwinięcie.

## Decisions

### D1. Szerokość mieszka w `agentChatStore`, obok zwinięcia

Ten sam sklep, ten sam `localStorage`, ten sam wzorzec odczytu odpornego na `Storage`,
który rzuca (Safari w trybie prywatnym — `loadExpanded` już to robi). Klucz osobny od
`terminal.agentChat.v1`, bo tamten trzyma jedno słowo (`"expanded"`), a nie obiekt;
dopisanie liczby do niego wymagałoby przepisania formatu i zgadywania przy odczycie
starej wartości.

Odrzucone: stan lokalny w `AgentChat.tsx` z zapisem w efekcie. Krótsze, ale wtedy
szerokość znika przy każdym odmontowaniu panelu i nie da się jej odczytać w teście sklepu,
gdzie stoi już zwinięcie.

Odrzucone: CSS `resize: horizontal`. Natywne i darmowe, ale działa tylko w prawo od
elementu, nie da się go ograniczyć w obie strony bez `max-width` liczonego w JS i nie ma
obsługi klawiatury — a wymaganie mówi wprost, że chwyt ma ją mieć.

### D2. Chwyt to element `separator` na krawędzi, nie cień na `border`

Wąski pasek (kilka pikseli, z powiększonym obszarem trafienia) o roli `separator`,
`aria-orientation="vertical"`, `tabIndex={0}` i `aria-label` mówiącym, co robi. Strzałki
zmieniają szerokość skokiem stałej wielkości; `Home`/`End` skaczą do granic. Ciągnięcie
myszą przez `pointerdown` + `setPointerCapture`, żeby ruch poza panel nie gubił chwytu.

Wartości `aria-valuenow`/`min`/`max` w pikselach — czytnik i tak podaje je liczbowo, a
procent liczony od okna zmienia się przy zmianie rozmiaru okna, więc kłamałby po fakcie.

### D3. Granice: dolna stała, górna liczona z okna

Dolna to szerokość, poniżej której nagłówek panelu przestaje się mieścić — jedna liczba w
kodzie, wyprowadzona z tego, co w nagłówku stoi. Górna to ułamek szerokości okna, nie
stała: na monitorze 4K stała granica byłaby przypadkowa, a na laptopie zabrałaby zakładkę.

Sprowadzanie do granicy dzieje się przy odczycie i przy zmianie rozmiaru okna, nie tylko
przy ciągnięciu — zapamiętana szerokość z szerszego monitora nie może wjechać na wąskie
okno dosłownie. To jest treść scenariusza "Okno węższe niż zapamiętana szerokość".

### D4. Szerokość idzie w `style`, nie w klasę

Klasa `w-115` znika na rzecz `style={{ width }}`. Tailwind nie ma klasy dla wartości
z sklepu, a generowanie nazw klas w locie jest dokładnie tym, czego jego skaner nie widzi.
Reszta wyglądu zostaje klasami.

## Risks / Trade-offs

- **Ciągnięcie przerysowuje wykres na każdą klatkę** → wykres i tak reaguje na
  `ResizeObserver`, ten sam, który obsługuje zwijanie; jeśli pomiar pokaże, że ciągnięcie
  zacina się przy sześciu wykresach w siatce, szerokość w trakcie ruchu idzie przez
  `requestAnimationFrame`, jak już robi to odczyt krzyżyka na wykresie. Nie zgadywać z
  góry.
- **Zapamiętana szerokość z popsutego wpisu** (`localStorage` ręcznie zmieniony, wartość
  nie-liczba) → odczyt zwraca domyślną, tak samo jak `loadActiveSessionId` przy
  niecałkowitym identyfikatorze.
- **`min-w-0` sąsiada jest warunkiem, żeby to w ogóle działało** → jest, z komentarzem;
  test terminala na oddawanie szerokości przy zwijaniu już stoi i obejmuje ten sam
  mechanizm.
