# Design — a-strategy-is-a-catalogue-entry

## Context

Motywacja w proposal.md.

**Poprawka do wzorca, naniesiona przy implementacji.** Artefakty pisane były z założeniem, że
szkielet modułu skopiujemy z `polymarket-data`. Tego modułu nie ma na `main` — żyje na
niescalonej gałęzi — więc gałąź tej zmiany brałaby zależność od cudzej pracy w toku. Wzorcem
jest zamiast tego `market-data` (lifespan, advisory lock, `/mcp`, `caller_access`) i
`workbench` (użycie `tc-runtime` zamiast własnego `db.py`). Układ jest ten sam; zmienia się
tylko, z którego pliku był przepisany.

Stan zastany, który kształtuje podejście: katalog wskaźników
market-data (wpis = deklaracja + czysta funkcja, jeden plik, maszyneria raz), wyzwalacze
zespołów w workbenchu (warunek progowy na polu wyniku narzędzia, czytany cyklicznie),
joby backfillu w market-data (historia dociągana na żądanie, granica u dostawcy) oraz
wzorzec szkieletu modułu z polymarket-data (lifespan z migracjami pod advisory lockiem,
config odmawiający startu, `/mcp` w tym samym procesie). Archiwum trzyma stronę bid;
REST wskaźników ma sufit 200 000 barów na zapytanie.

## Goals / Non-Goals

**Goals:**

- Jeden kontrakt wpisu strategii, który przeżyje trzecią strategię bez zmian w runtime.
- Jedna funkcja oceny wołana przez pętlę i backtest — warunek testu przyrostowe=wsadowe.
- Szew z workbenchem bez zmian w workbenchu: wyzwalacz na liczbie oczekujących setupów.

**Non-Goals:**

- Wykonanie na rachunku, w każdym trybie — moduł nie dostaje klienta trading-mcp ani bramy.
- Strategie tickowe, portfelowe, wolumenowe i niedeterministyczne (ML w `evaluate`) —
  każda z tych granic to osobna, świadoma zmiana kontraktu, żadna „przy okazji".
- Widoki terminala dla platformy — osobna zmiana, gdy będzie co oglądać.

## Decisions

**1. Wpis strategii jest kodem w obrazie; w bazie są tylko parametry.**
Logika (`evaluate`, deklaracja faktów) mieszka w repo modułu jak wpisy katalogu wskaźników;
baza trzyma wersjonowane zestawy parametrów i decyzje. Alternatywa — strategia jako dane
(DSL edytowalny w runtime, wzorem definicji zespołów) — odrzucona: czysta funkcja oceny
w DSL wymagałaby zbudowania własnego języka, a jego interpreter i tak byłby kodem do
wdrożenia; zespoły wersjonują graf rozmowy, nie logikę liczącą. Koszt tej decyzji: nowa
strategia = wdrożenie, i to jest koszt akceptowany — strategia bez przejrzanego kodu nie
powinna istnieć.

**2. Fakty wyłącznie z REST market-data (`POST /indicators/{symbol}`), nie z MCP i nie
z własnej matematyki.** Powierzchnia MCP archiwum jest odchudzona pod modele i ma limity
(10 wskaźników, 200 punktów serii) — właściwa dla agenta, za ciasna dla pętli. Liczenie
własne odrzucone: dwie implementacje tej samej matematyki rozjeżdżają się przy pierwszej
poprawce (ta sama racja, którą spec wyzwalaczy zapisał dla workbencha). Sufit 200 000
barów obsługuje klient modułu cięciem okien — logika strategii o nim nie wie.

**3. Backtest w tym samym module, nie osobnym.** Osobny moduł musiałby wołać `evaluate`
przez opublikowany kontrakt albo dzielić ją pakietem — pierwsze robi z każdej świecy
przebiegu żądanie sieciowe, drugie rozmnaża miejsca, w których logika może się rozjechać
z pętlą. Test przyrostowe=wsadowe porównuje funkcję samą ze sobą; najtańszy sposób, żeby
to była ta sama funkcja, to ten sam proces.

**4. Zapis decyzji niesie pełne fakty wejściowe, nie wskaźnik na archiwum.** Odtworzenie
decyzji ma działać niezależnie od retencji i ewentualnych korekt archiwum; fakty to wyniki
wskaźników (strefy, markery, liczby), nie surowe świece, więc rozmiar jest ograniczony
z natury. Alternatywa „zapisz zapytanie, odtwórz z archiwum" odrzucona: wiąże odtwarzalność
decyzji z niezmiennością cudzej bazy.

**5. Moduł nazywa się `strategy`, port 8080.** 8040 i 8050 pozostają spalone (stare adresy
market-mcp i teams-mcp w zabłąkanych `.env` mają dalej czytać się jako „nic tam nie
słucha"). Klucz advisory locka = 8080, zgodnie z konwencją „klucz to port modułu".

**6. Model kosztów backtestu startuje jako jawny parametr per instrument.** Pomiar
rozkładu spreadu ze strumienia kwotowań bramy to lepsze źródło, ale wymaga zbierania,
którego nikt jeszcze nie robi; raport i tak nazywa swój model kosztów, więc podmiana
parametru na pomiar nie zmienia kontraktu. Odrzucone: koszty „domyślnie zero" — spec
wprost zakazuje raportu bez modelu kosztów.

## Risks / Trade-offs

- [Kontrakt wpisu projektowany „na zapas" pod strategie, których nikt nie napisał] →
  zamrożenie nawyków platformy dopiero po dwóch realnych wpisach (baseline, potem SMC);
  żadnych abstrakcji ponad to, czego te dwa używają. Trzecia strategia będzie właściwym
  testem kontraktu.
- [Pętla dokłada obciążenie archiwum; budżet dostawcy to 10 żądań/s na konto] → ocena
  wyłącznie na domknięciu świecy (M15+, nie tick), fakty jednym zapytaniem na strategię,
  okna cięte pod sufit; backfill zlecany jobami archiwum, nie własnym pobieraniem.
- [Świece bid zaniżają koszty; wynik backtestu może schlebiać strategii] → model kosztów
  obowiązkowy w raporcie i nazwany po imieniu; porównania tylko przy identycznych kosztach.
- [Baza rośnie od snapshotów decyzji] → snapshot trzyma wyniki wskaźników, nie świece;
  retencja decyzji to parametr modułu, odmowy z powodu danych rozróżnialne i tanie.

## Migration Plan

Kolejność produkcyjna jak przy narzędziach workbencha — ustawienia przed obrazem:
`terraform apply` (App Service, tożsamość zarządzana, wpis tożsamości modułu do
`allowed_applications` i `REST_CALLER_APPLICATION_IDS` market-data, baza `strategy`
z nadaniem własności schematu) musi wylądować, zanim wdrożenie da obraz, który te
ustawienia egzekwuje. Odwrót: dezaktywacja strategii (pętla milknie), usunięcie
wyzwalaczy po stronie workbencha, w ostateczności zdjęcie App Service — nic nie zależy
od modułu, więc odwrót nie dotyka reszty stacku.

## Open Questions

- Który instrument i który baseline pierwszy (przecięcie średnich czy wybicie kanału) —
  decyzja operatora przy pierwszym wpisie; nie zmienia speców ani zadań.
- Kiedy zastąpić parametryczny spread pomiarem ze strumienia kwotowań — po pierwszym
  pełnym przebiegu backtestu, osobną, małą pracą.
