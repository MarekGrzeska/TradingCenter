## Context

Pętla przechodzi przez tematy w `_discover` ([ingest.py](modules/workbench/youtube_data/ingest.py)): szuka, odfiltrowuje znane
i rozstrzygnięte, przesiewa modelem jednym wywołaniem i zapisuje kandydatów; `record_topic_run` nadpisuje `last_run_at`. Błąd
źródła nie zapisuje przebiegu, co jest zamierzone — temat jest wtedy próbowany w następnym przebiegu pętli. Przebiegów
z `skipped` dziś nie ma: przy pustym dniu pętla po tematach po prostu się kończy.

## Goals / Non-Goals

**Goals:** każda próba i jej wynik widoczne po fakcie; raport tani w zapisie; historia nie rośnie bez końca.

**Non-Goals:** koszt przebiegu w jednostkach i tokenach (jest w `usage` per doba, a przypisanie go do przebiegu wymagałoby
rozdzielania licznika); historia przebiegów kanałów; zmiana terminu próby po porażce.

## Decisions

**1. Jedna tabela `topic_runs`, bez klucza obcego do `topics`.** Tak jak `videos` nie odwołują się do `channels`: lista jest
powodem, dla którego szukaliśmy, a nie tym, co przechowujemy; wpis niesie frazę z chwili przebiegu. Alternatywa — liczniki
w `topics` — gubi historię, a odtwarzanie z `candidates` nie pokazuje przebiegów bez kandydatów ani porażek, czyli dokładnie
tego, czego operatorowi brakuje.

**2. `skipped` raz na temat na dobę UTC.** Pominięcie z powodu dnia powtarza się w każdym przebiegu pętli aż do północy;
wpis na każdy przebieg to kilkanaście identycznych wierszy dziennie na temat i zagłuszone prawdziwe zdarzenia. Test „czy
dziś już było” to jedno zapytanie po indeksie `(topic_id, ran_at)`. `failed` zapisuje się zawsze, bo każda porażka jest
osobną próbą i jej przyczyna może się zmienić.

**3. Retencja przy zapisie, 30 dni.** Usunięcie `WHERE ran_at < now - 30 d` w tej samej transakcji co wpis, po indeksie
`ran_at`; nie potrzeba osobnego zadania ani timera. Alternatywa — zadanie sprzątające — dokłada pętlę, którą ktoś musi
pilnować.

**4. Przyczyna nieprzesiania jest częścią przesiewu, nie dopiskiem pętli.** `_screen` zwraca dziś trzy rzeczy i wiele
powodów, dla których nie ma werdyktu, ginie w logu; dostaje czwartą — powód (`no_model`, `day_spent`, `unusable`, `failed`) —
żeby wpis nie musiał go zgadywać.

**5. Wynik ostatniego przebiegu w `GET /topics`.** Jedno zapytanie `LATERAL` z jednym odczytem indeksu na temat, dla wszystkich
tematów (jest ich najwyżej `MAX_TOPICS`), zamiast sprawiać, żeby terminal ściągał całą historię po jedną linijkę.

## Risks / Trade-offs

- [Wiersz na przebieg przy tematach co 15 minut] → 30 dni retencji ogranicza tabelę do kilkudziesięciu tysięcy wierszy
  przy pełnej liście; `db-cost-check` mierzy zapis i odczyt.
- [Pominięcie raz na dobę ukrywa, że pętla przechodziła wielokrotnie] → wynik i przyczyna są te same, a liczba przejść nie jest
  informacją, której operator szuka.

## Migration Plan

Migracja `0007` tworzy pustą tabelę i indeksy; wykonuje się sama przy starcie. `downgrade` usuwa tabelę. Wcześniejszych
przebiegów nie da się odtworzyć, więc historia zaczyna się od wdrożenia.
