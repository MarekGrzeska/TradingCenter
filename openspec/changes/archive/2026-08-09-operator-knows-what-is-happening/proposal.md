## Why

Wieczorem 9 sierpnia zlecenie dociągnięcia historii stało czterdzieści minut, pokazując „running",
i z zewnątrz nie dało się go odróżnić od zlecenia, które pracuje — a gdy w końcu ruszyło, zrobiło
trzydzieści pięć tysięcy świec w minutę. Tego samego wieczoru operator wszedł na terminal, zobaczył
w rogu napis „signed out" i musiał sam się domyślić, że ma poszukać przycisku.

Trzy różne miejsca, jedna przyczyna: operator nie widzi, co się dzieje, i nie wie, czego się od
niego oczekuje. Ta zmiana zamyka to z obu stron — mechanizm mówi, co robi, a terminal pyta o zgodę
zawsze w ten sam sposób.

## What Changes

**Pętla robocza przeżywa własną awarię.** Dziś pojedynczy błąd przy przejmowaniu kawałka kończy
workera na zawsze i do restartu modułu nikt już niczego nie pobierze. Awaria MUST kosztować jedno
podejście, nie cały mechanizm: pętla odnotowuje ją, odczekuje i próbuje dalej.

**Zlecenie mówi, kiedy ostatnio coś się w nim wydarzyło.** Kawałki znają swoje `started_at` i
`finished_at`, ale nic tego nie wystawia. Zlecenie zaczyna podawać moment ostatniej aktywności, a
zakładka `Data History` go pokazuje — „stoi" widać w dziesięć sekund, nie po czterdziestu minutach.

**Ponowienie przestaje obiecywać węziej, niż robi.** Zakres ponowienia zostaje bez zmian — jedno
ponowienie na całe zlecenie, wszystkie jego pary. Zmienia się miejsce: przycisk znika z wiersza
pary, a kliknięcie wiersza otwiera dialog całego zlecenia, w którym widać każdą jego parę, co
zawiodło i z jakich powodów, i z którego ponawia się całość — jawnie nazwaną jako całość.

**Terminal sam zaczyna logowanie.** Operator bez tożsamości nie zobaczy w terminalu niczego, więc
terminal MUST NOT czekać, aż ten znajdzie przycisk. Praca lokalna bez skonfigurowanej tożsamości
zostaje nietknięta, a wskaźnik z przyciskiem zostaje jako droga wyjścia, gdy automat zawiedzie.

**Każde potwierdzenie jest dialogiem.** Dziś terminal pyta na dwa sposoby: dialogiem modalnym
(kreator, kasowanie — dwie osobne, powielone implementacje) i wierszem doklejonym do tabeli
(ponowienie). Wprowadzamy jedną zasadę i jeden wspólny dialog, z którego korzystają wszystkie
miejsca pytające o zgodę.

## Capabilities

### New Capabilities
- `terminal-dialogs`: jak terminal pyta operatora o zgodę i o decyzję — forma modalnego dialogu
  jako jedyna dopuszczona, wspólne zachowania każdego z nich (nazwanie skutku, akcja potwierdzająca
  i wycofująca, praca w toku, błąd pokazany w dialogu, klawiatura i fokus) oraz obowiązek
  wyprowadzania ich wszystkich z jednego miejsca.

### Modified Capabilities
- `market-data-jobs`: pętla robocza MUST przeżyć awarię przy przejmowaniu pracy, a zlecenie MUST
  podawać moment swojej ostatniej aktywności.
- `terminal-collection-history`: praca w toku MUST pokazywać, kiedy ostatnio coś się wydarzyło;
  ponowienie przenosi się z wiersza pary do dialogu całego zlecenia i MUST być nazwane jako
  ponowienie zlecenia.
- `terminal-identity`: terminal MUST sam rozpocząć logowanie, gdy tożsamość jest skonfigurowana, a
  operator nie jest zalogowany — bez pętli przekierowań i bez ruszania trybu lokalnego.

## Impact

**market-data** — `jobs/runner.py` (pętla workera), `jobs/models.py` i `jobs/store.py` (moment
ostatniej aktywności zlecenia), `contract.py` (`JobPairViewOut`, `JobOut`), `routers/jobs.py`.
Kontrakt rośnie o pole; żadne istniejące pole nie znika, więc nie jest to zmiana łamiąca.

**terminal** — `src/history/CollectionHistoryView.tsx` (ostatnia aktywność, wiersz klikalny, dialog
zlecenia, koniec potwierdzenia w tabeli), `src/data/contract.generated.ts` (regeneracja z OpenAPI),
`src/app/TopBar.tsx` i `src/auth/*` (automatyczne logowanie), nowy wspólny dialog w `src/ui/`,
`src/instruments/AddInstrumentWizard.tsx` i `src/instruments/InstrumentsView.tsx` (przejście
dwóch istniejących dialogów na wspólny komponent).

Bez zmian w bazie danych i bez migracji: moment ostatniej aktywności jest wyliczany z kawałków,
które już go znają.
