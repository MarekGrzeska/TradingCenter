## Context

Zob. `proposal.md` — Why. Tu tylko to, co ogranicza rozwiązanie.

Metrykę emituje `telemetry.py` jako obserwowalny gauge OpenTelemetry: `refresh_loop` co
interwał liczy wiek każdej pary, a eksporter odczytuje ostatnią wartość, kiedy sam uzna, że
pora. Klucz jest już parą `(symbol, resolution)`, więc rozdzielczość jest na miejscu — nie
trzeba jej nikąd donosić.

Zapas na dostarczenie świecy jest zmierzony i zapisany w `tracking.py`: `DELIVERY_GRACE`
to trzy minuty, ustalone obserwacją 8 sierpnia (zamknięta świeca minutowa docierała 52–169
sekund po zamknięciu okresu). Obok stoi `STALE_AFTER_PERIODS = 2` — po tylu okresach moduł
nazywa parę `STALLED` w swoim własnym API.

Ograniczenie po stronie Azure: `azurerm_monitor_metric_alert` waliduje istnienie metryki w
momencie `apply`. Reguła założona na metrykę, która nigdy nie dotarła do Application Insights,
jest odrzucana — dlatego dziś stoi tam `skip_metric_validation = true`.

## Goals / Non-Goals

**Goals:**
- Jeden próg, który znaczy to samo dla `MINUTE` i dla `WEEK`.
- Alarm, który daje się zgasić i zapalić, więc nadaje się do czytania.
- Zdjęcie `skip_metric_validation` — Azure ma sam potwierdzić, że reguła stoi na czymś, co
  istnieje.

**Non-Goals:**
- Przenoszenie logiki `STALLED` z `tracking.py` do alarmu. Alarm jest siatką bezpieczeństwa,
  nie drugą kopią stanu pary; zostaje grubszy od wskaźnika w terminalu i taki ma być.
- Alarmowanie per para. Azure widzi wymiary metryki, ale reguła zostaje jedna, na maksimum —
  awaria, która dotyka jednej pary, i awaria, która dotyka wszystkich, mają obudzić tak samo.
- Kalendarz sesji. Metryka już teraz pomija pary, których rynek gateway zgłasza jako
  zamknięty, i to zostaje jedynym mechanizmem „w godzinach handlu".

## Decisions

**Nowa metryka obok starej, nie zamiast.** `market_data.candle_age_periods` dochodzi,
`market_data.candle_age_seconds` zostaje. Powód jest praktyczny: liczba okresów nadaje się na
próg i nie nadaje się do diagnozy — z „4,2 okresu" nie odczyta się godziny, o której zbieranie
stanęło, a to jest pierwsze pytanie po awarii. Rozważane było zastąpienie: oszczędza jeden
strumień punktów, kosztuje historię, której w portalu nie da się odtworzyć wstecz.

**Spóźnienie liczone po odjęciu zapasu, nie surowy wiek podzielony przez okres.** Surowy
iloraz wygląda prościej i wraca dokładnie do problemu, który `DELIVERY_GRACE` już raz
rozwiązało: zdrowa para `MINUTE` ma wiek do 229 sekund (jeden okres plus zmierzone
opóźnienie), czyli 3,8 „okresu" — powyżej każdego rozsądnego progu. Po odjęciu trzech minut
zdrowa para `MINUTE` siedzi poniżej jednego okresu, a zdrowa `DAY` — tak samo, bo trzy minuty
to przy dobie zero. Wartość jest podłogowana do zera, żeby świeża świeca nie schodziła w
ujemne.

**Próg trzy okresy.** Wskaźnik w module mówi `STALLED` po dwóch okresach plus zapas; alarm
produkcyjny ma być od niego grubszy, więc trzy. Przy `MINUTE` to trzy minuty ponad zapas, przy
`DAY` — trzy doby. To ostatnie brzmi jak dużo i jest właściwe: para dzienna, która przegapiła
trzy świece, jest zepsuta niezależnie od tego, jak długo trwała cisza w sekundach, a dobierać
osobny próg dla każdej rozdzielczości to dokładnie ta konfiguracja, której ta zmiana się
pozbywa.

**`DELIVERY_GRACE` i `STALE_AFTER_PERIODS` czytane z `tracking.py`, nie skopiowane.** Obie
stałe mają w tym module dokładnie jedno znaczenie i jedno miejsce. Kopia w `telemetry.py`
rozjechałaby się z oryginałem przy pierwszym pomiarze, który zmieni zapas — a ten już raz był
zmieniany na podstawie obserwacji.

## Risks / Trade-offs

**Nowa metryka nie istnieje w Application Insights w chwili `terraform apply`, więc Azure
odrzuca regułę bez `skip_metric_validation`.** → Kolejność wdrożenia jest częścią zmiany, nie
przypisem: najpierw `market-data`, potem infrastruktura. Weryfikacja jest ręczna i tania —
metryka musi być widoczna w portalu, zanim reguła zostanie założona. To jedyny krok tej
zmiany, którego nie da się zrobić w dowolnej kolejności.

**Alarm może być głuchy między jednym a drugim krokiem.** → Jest głuchy od 9 sierpnia, więc
okno niczego nie pogarsza; kończy się w tej samej sesji operatora.

**Próg trzech okresów przy `WEEK` to trzy tygodnie ciszy, zanim cokolwiek zawoła.** → Świadome.
Para tygodniowa, która nie dostała świecy, jest widoczna w terminalu jako `STALLED` po dwóch
okresach — alarm nie jest jedynym kanałem, tylko ostatnim. Alternatywa (osobny próg per
rozdzielczość) wraca do konfiguracji, którą ta zmiana usuwa.

**Metryka w okresach ukrywa czas.** → Dlatego sekundowa zostaje. Alarm woła, sekundy mówią
kiedy.

## Migration Plan

1. Wdrożyć `market-data` z obiema metrykami. Reguła alarmu stoi jeszcze na starej — dalej
   zapalona, dalej bezużyteczna, ale nic nie psuje.
2. Potwierdzić w Application Insights, że `market_data.candle_age_periods` ma punkty. To jest
   warunek następnego kroku, nie formalność.
3. `terraform apply` — reguła przechodzi na nową metrykę, próg trzy, bez
   `skip_metric_validation`. `apply` robi operator; CI planuje i nigdy nie stosuje.
4. Sprawdzić, że alarm zszedł do stanu spoczynku.

Wycofanie: `terraform apply` z poprzedniej rewizji `monitoring.tf` przywraca starą regułę
(razem z `skip_metric_validation`, bo starej metryki Azure też nie zwaliduje inaczej). Kod
modułu nie wymaga wycofania — druga metryka nikomu nie przeszkadza.
