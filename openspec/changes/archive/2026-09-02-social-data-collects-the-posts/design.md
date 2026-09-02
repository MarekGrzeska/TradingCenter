## Context

Zobacz `proposal.md` — Why. Stan, który kształtuje podejście: `polymarket-data` przeniósł z tej
samej aplikacji archiwum cen i zostawił warstwę alertową nietkniętą, nazywając ją w swoim README
robotą workbencha. Ta zmiana bierze z niej pierwszy kawałek i musi rozstrzygnąć, czy tamto zdanie
nadal obowiązuje.

Ograniczenia: moduł nie importuje modułu; wzbogacenie jest własnością wiersza, więc obcy proces
mógłby je zapisać wyłącznie przez kontrakt zapisu, którego tu nie ma i nie chcemy; agent ma dostać
narzędzia, więc to, po czym da się filtrować, musi istnieć przed pytaniem.

## Goals / Non-Goals

**Goals:**
- Archiwum postów, które jest prawdziwe: zbiór niezależny od tego, kto patrzy, i jawny początek.
- Ocena wpływu jako **dane**, po których filtruje kontrakt i narzędzie — nie jako odpowiedź modelu
  liczona przy pytaniu.
- Drugie źródło postów jako plik, nie jako przebudowa.

**Non-Goals:**
- Alerty, progi powiadomień, Telegram. Kolumny po nich nie zostają.
- Agregator newsów z aplikacji źródłowej — inny upstream, inny kształt, osobna decyzja.
- Handel czymkolwiek na podstawie postów. Moduł niczego nie decyduje.

## Decisions

### Osobny moduł, nie rozszerzenie istniejącego

`social-data` staje obok `polymarket-data`, a nie w nim.

Rozważone i odrzucone: **wstawienie do `polymarket-data`** — to moduł opisany jako jedyne drzwi do
Polymarketu, a RSS Trumpa nimi nie jest; jego własne README nazywa tę warstwę nieprzeniesioną, więc
dołożenie jej tam bez zmiany tamtego zdania byłoby cichym odwróceniem decyzji. **Wstawienie do
workbencha** — workbench nie jest archiwum niczego; pętla zbioru i baza postów zrobiłyby z niego
trzecią powierzchnię w procesie, który już ma dwie.

### Ocena powstaje w module przy zbiorze, a workbench zachowuje swój osąd

To jest rozstrzygnięcie zdania z README `polymarket-data` („ocena wagi zdarzenia jest robotą
workbencha"), a nie jego złamanie. Rozdzielamy dwie rzeczy, które to zdanie zlepia:

- **Odczyt** — „model X o godzinie T dał temu postowi 7 i te tematy". To fakt tej samej klasy co
  „rynek o T wyceniał 0,63". Moduł go przechowuje, ostemplowanego, i nie ma tu własnej opinii.
- **Osąd** — „czy to zmienia moją pozycję". Zostaje w workbenchu, robiony na tych danych.

Rozważona alternatywa: **osąd przy pytaniu, w workbenchu**. Odrzucona z trzech policzalnych
powodów: narzędzie nie ma po czym filtrować (`min_score` przestaje istnieć), ta sama treść dostaje
różne oceny w dwóch rozmowach, a tokeny idą per pytanie zamiast raz per post. Druga alternatywa —
**workbench liczy i zapisuje przez kontrakt zapisu** — wymagałaby trasy piszącej, uprawnienia do
niej i harmonogramu po stronie workbencha; trzy nowe rzeczy po to, żeby wynik wylądował tam, gdzie
i tak ma stać.

### Odczyt jest nadpisywany, nie wersjonowany

Przy poście stoi jeden bieżący odczyt. Zmiana modelu albo instrukcji go nadpisuje.

Rozważone: **osobna tabela odczytów z historią**. Odrzucone — nikt nie odtwarza „co model myślał
w zeszłym tygodniu o poście sprzed miesiąca", a każde zapytanie o listę płaciłoby złączeniem po
najnowszym odczycie. Rachunek za model zostaje mimo to (`ai_usage`), bo pieniądz wydano także za
odczyt, który już nie obowiązuje — i to jest jedyna rzecz z tej rodziny, którą warto trzymać
w historii.

### Nazwa szersza niż źródło, z ceną zapłaconą dziś

Moduł nazywa się `social-data`, mimo że dziś czyta jedno źródło. Uogólnienie kosztuje **trzy
rzeczy teraz**: nazwa źródła wchodzi do klucza tożsamości posta, autor jest kolumną, a pobieranie
stoi za protokołem z jedną implementacją.

Rozważone: **`truth-social` i zmiana nazwy później**. Odrzucone — przemianowanie modułu ciągnie
port, bazę, tożsamość w Entra, ustawienia workbencha i dwa wygenerowane kontrakty. Trzy pola dziś
są tańsze niż to. Rozważone też: **zbudować drugie źródło od razu**, żeby protokół był zmierzony,
a nie wymyślony — odrzucone, bo drugiego źródła nikt jeszcze nie potrzebuje, a protokół z jedną
implementacją da się poprawić, gdy przyjdzie druga.

### Własny cienki klient modelu, nie `tc-openai`

Rozważone: **wzięcie `tc-openai`**, tak jak robi to workbench. Odrzucone przy warunkach z
`docs/architecture.md`: paczkę bierze się, gdy kod jest już ręczną kopią mierzalnie identyczną albo
gdy jest nowy i identyczny dla każdego konsumenta od pierwszego dnia. Tu nie zachodzi żadne z tych:
`tc-openai` jest strumieniowy i narzędziowy, a moduł potrzebuje jednego wywołania ze sztywnym
schematem odpowiedzi. Drugi konsument ciągnąłby cały strumień i warstwę narzędzi, żeby nie użyć
ani jednego.

### Wzbogacanie w tej samej pętli co zbiór

Jeden task w `lifespan` robi: zbierz → przetłumacz nowe → oceń nieocenione.

Rozważone: **osobna pętla albo harmonogram**. Odrzucone — dwie pętle nad tą samą tabelą wymagają
uzgodnienia, kto czego dotyka, a jedyne, co dają, to możliwość wzbogacania w innym rytmie niż
zbiór, której nikt nie potrzebuje. Błąd modelu nie może wywrócić zbioru, więc wzbogacanie jest
w tej pętli krokiem osobno łapiącym błędy.

### Cztery narzędzia, z podziałem na skrót i pełną treść

Rozważone: **jedno narzędzie z siedmioma parametrami** — model gorzej trafia w takie wywołanie,
a opis rośnie tak samo. Rozważone: **jedenaście jak w `market-data`** — tam wynika to z jedenastu
różnych pytań o świece; tutaj pytania są trzy plus stan. Podział na skrót i pełną treść jest
arytmetyczny: doba postów w pełnej treści to okno kontekstu wydane, zanim model cokolwiek zrobi.

### Port 8090

Rozważone: **8040 albo 8050**, formalnie wolne. Odrzucone — `CLAUDE.md` opisuje je jako porty,
których stary `.env` ma się czytać jako serwer wyłączony. Zajęcie któregoś zamienia „nic nie
odpowiada" na „odpowiada cudzy moduł", czyli błąd trudniejszy.

### Zakładka pocketa bez zdolności w `openspec/specs/`

Pocket w całości powstał zwykłą ścieżką i nie ma dziś ani jednego pliku w `openspec/specs/`. Ta
zmiana tego nie odwraca przy okazji: terminal dostaje `terminal-social`, bo tak wygląda każdy jego
ekran, a praca nad zakładką pocketa jest w `tasks.md`. Odwrócenie tej konwencji jest osobną
decyzją, nie skutkiem ubocznym.

## Risks / Trade-offs

- **Treść posta trafia do modelu i dalej do agenta — to cudzy tekst, nie instrukcja.** → Odpowiedź
  wzbogacania jest wymuszona sztywnym schematem (tematy, liczba 1–10), więc post nie ma jak
  rozszerzyć swojego wpływu poza te dwa pola; narzędzia wydają treść jako dane posta, a nie jako
  polecenie. Ryzyko zostaje po stronie agenta czytającego treść i tam jest znane.
- **Źródło jest nieoficjalne i jednoosobowe** — może zniknąć albo zmienić kształt dokumentu. →
  Protokół źródła, testy parsera na zapisanym dokumencie, a stan modułu odróżnia ciszę źródła od
  cichego dnia, więc awaria będzie widoczna, a nie cicha.
- **Wykrywanie podania dalej opiera się na tekście w treści** (tak jest u źródła). → Pole jest
  opisowe i niczym nie steruje; złe rozpoznanie kosztuje znacznik na karcie, nie dane.
- **Rachunek za model rośnie z liczbą postów.** → Okno zamiast całego archiwum, jeden odczyt na
  post, brak backfillu i zapis zużycia przy poście, żeby koszt był widoczny, zanim urośnie.
- **Zmiana modelu przesuwa oceny i nie da się porównać „przed" z „po".** → Świadome: stempel
  modelu jest w odpowiedzi, a historia oceny nie jest tu wartością.
- **Wdrożenie obrazu przed `apply`** daje przerwę, w której moduł odmawia workbenchowi. →
  Kolejność z `CLAUDE.md`: ustawienia i zapis dostępu przed obrazem; cofnięcie to wyczyszczenie
  `SOCIAL_MCP_URL` i restart.

## Migration Plan

Moduł jest nowy, więc nie ma czego migrować — jest kolejność, w której wdrożenie nie robi przerwy:

1. Baza `social` powstaje, operator wykonuje na niej `scripts/grant-schema-ownership.sql` — raz.
2. `apply` zakłada App Service, tożsamość, i wpisuje tożsamość workbencha do zapisu dostępu modułu.
3. Wdrożenie obrazu; moduł sam migruje bazę pod blokadą przy starcie, sonda pyta o `/health`.
4. Dopiero potem `SOCIAL_MCP_URL` w workbenchu i restart — do tego momentu workbench działa bez
   czwartego serwera narzędzi, co jest stanem wspieranym.
5. Cofnięcie: wyczyścić `SOCIAL_MCP_URL`, zrestartować workbench. Moduł zostaje i dalej zbiera —
   nikt nie traci danych przez wycofanie narzędzi.

## Open Questions

- Odstęp zbioru i próg „wysokiego wpływu" na ekranie (dziś zakładamy 5 minut i 6/10, za źródłem) —
  do ustawienia po pierwszym tygodniu obserwacji, bez zmiany specyfikacji.
- Czy pocket ma mieć ten sam próg co terminal, czy wyższy — telefon otwiera się na sekundy.
