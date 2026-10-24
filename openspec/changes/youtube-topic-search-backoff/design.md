## Context

`DataApiSource._get` liczy jednostki, gdy tylko YouTube odpowie — także na odmowę — bo odrzucone zapytanie zjada przydział;
błąd sieci (brak odpowiedzi) nie jest liczony. Oba kończą się dziś tym samym `SourceUnavailable`, a pętla po porażce nie zmienia
`last_run_at`, więc temat jest próbowany w każdym przebiegu. `last_run_at` jest też początkiem okna wyszukiwania (`publishedAfter`).

## Goals / Non-Goals

**Goals:** temat, który zawodzi, kosztuje najwyżej tyle, co temat, który działa; chwilowy brak sieci nie wstrzymuje tematu na godziny.

**Non-Goals:** odroczenie wykładnicze; wyłącznik dla całego źródła po porażce jednego tematu.

## Decisions

**1. Odroczenie o własny odstęp tematu, nie o stałą.** Wtedy koszt porażki jest z definicji równy kosztowi sukcesu (jedno
wyszukiwanie na odstęp), niezależnie od tego, jak operator ustawił temat. Stała (np. godzina) przy temacie co 6 h dalej
kosztowałaby sześć razy więcej niż działający temat. Odroczenie wykładnicze daje szybszy powrót po krótkiej awarii, ale
krótka awaria to zwykle brak odpowiedzi, który i tak jest ponawiany od razu (decyzja 2).

**2. Zapłacone kontra niezapłacone.** Nowy wyjątek `SourceRefused` (podklasa `SourceUnavailable`, więc istniejące obsługi
działają) dla odpowiedzi, za którą policzono jednostki: odmowa, kod błędu, odpowiedź nie-JSON. Brak odpowiedzi zostaje
`SourceUnavailable`. Tylko zapłacona porażka i `QuotaExceeded` odraczają temat. Alternatywa — odraczać każdą porażkę —
wstrzymywałaby temat na 6 h po chwilowym błędzie sieci, który nic nie kosztował.

**3. Osobna kolumna `topics.retry_at`, nie przesunięcie `last_run_at`.** `last_run_at` wyznacza okno wyszukiwania; gdyby porażka
je przesuwała, filmy opublikowane między ostatnim sukcesem a porażką nigdy nie zostałyby znalezione.

## Risks / Trade-offs

- [Przyczyna odrzucenia leży po stronie klucza lub projektu Google i dotyczy wszystkich tematów] → pierwszy przebieg po
  wznowieniu zapłaci raz za każdy temat (8 × 101), potem każdy czeka swój odstęp: najwyżej tyle, ile kosztowały działające tematy.
- [Operator chce ponowić od razu] → wstrzymanie i wznowienie tematu nie zdejmuje odroczenia; zdejmuje je udane wyszukiwanie.
  Akceptowalne na teraz; w razie potrzeby osobna zmiana.

## Migration Plan

Migracja `0008` dodaje pustą kolumnę; tematy startują bez odroczenia. `downgrade` usuwa kolumnę.
