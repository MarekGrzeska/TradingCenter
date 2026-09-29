## Why

Operator śledzi konflikt USA–Iran, a news o Ormuzie czy rozmowach w Nowym Jorku rusza ropą i złotem
szybciej, niż pokaże to świeca. Dziś archiwum `/social` zna jedno konto na jednym portalu. Rozpoznanie
z 29 września (`docs/zrodla-newsow.html`) zmierzyło kilkanaście darmowych feedów RSS, które odpowiadają
dziś, także na uczciwy User-Agent. Każdy dzień bez zbierania to dzień, którego archiwum już nie będzie
miało — dlatego ta zmiana robi tylko zbiór i ekran, a model dojdzie osobną zmianą.

Druga połowa powodu to **opóźnienie**. Wartość newsa dla rynku zależy od tego, jak późno dotarł. Źródło
szybkie i źródło godzinę spóźnione wyglądają na liście tak samo, dopóki system nie zmierzy różnicy
i jej nie pokaże.

## What Changes

- **Newsy mieszkają w pakiecie `social_data`, w bazie `social`, pod `/social/news`**. To decyzja
  operatora podjęta ze względu na czas: merge wystarcza, żeby zbiór ruszył, bo migracja idzie
  w `lifespan`. Nie trzeba `apply`, `grant-schema-ownership.sql` ani miejsca w budżecie połączeń.
  Przyszła zmiana z modelem dostanie gotową maszynerię wzbogacania tego pakietu. Newsy mają własne
  tabele: to inny kształt niż post (tytuł, lead, wydawca, feed), a wzbogacanie postów ich nie dotyka.
- **Druga pętla w pakiecie: zbiór newsów z zadeklarowanej listy feedów RSS**, z warunkowym GET.
  Źródło jest wpisem danych, a nie plikiem kodu. Lista startowa to pełna lista z rozpoznania, razem
  z Al Jazeerą, ale tylko jej RSS, bez relacji na żywo.
- **Deterministycznie, bez modelu i bez filtra słów kluczowych przy zbiorze.** Pętla zapisuje
  wszystko, co feed niesie, po angielsku, tak jak podało źródło. Filtr przy zbiorze gubiłby dane
  bezpowrotnie, a zawężanie jest pytaniem do odczytu.
- **Opóźnienie jest mierzone i publikowane per news i per źródło.** Liczone z czasu publikacji,
  momentu pierwszego zobaczenia i poprzedniego udanego pobrania. Dzięki temu da się oddzielić
  spóźnienie źródła od spóźnienia własnej pętli.
- **Nowe trasy odczytu** pod `/social/news`: lista newsów z oknem i zawężeniami, oraz stan źródeł
  z opóźnieniami. Trafiają do istniejącego `contract.social.generated.ts`.
- **Zakładka „News” w terminalu i ekran News w pocket**: lista newsów z opóźnieniem przy każdym oraz
  zestawienie źródeł, czyli które jest szybkie, które stoi i które odmawia.
- **Retencja 28 dni i przycisk „zachowaj”.** Newsy to strumień, a nie archiwum postów: pętla sama
  usuwa starsze niż okres retencji, chyba że operator oznaczył je na karcie w terminalu albo
  w pocket. Znacznik zachowania to **pierwsza trasa zapisująca w `/social`**. Wymóg „kontrakt
  wyłącznie czyta” dostaje dokładnie ten jeden wyjątek i nic poza nim.
- **Poza zakresem:** tłumaczenie, ocena wpływu, alerty na Telegram, narzędzia dla rozmowy,
  deduplikacja tego samego newsa między źródłami, relacje na żywo (JSON-LD Guardiana i CNN) i pobieranie stron
  artykułów po pełny tekst (feed niesie go tylko czasem).
  Wszystko to czeka na osobne zmiany, a schemat żadnej z nich nie blokuje.

## Capabilities

### New Capabilities

- `social-data-news-ingest`: skąd i jak często pakiet pobiera newsy, czym jest źródło, tożsamość
  newsa, co robi z feedem milczącym, odmawiającym albo nieparsowalnym, czego nie filtruje i jak
  długo news żyje.
- `social-data-news-latency`: jak mierzone jest opóźnienie newsa i źródła, co jest granicą dolną,
  a co górną, oraz jak traktowane są braki i czasy z przyszłości.
- `social-data-news-api`: trasy odczytu newsów i stanu źródeł, okno i zawężenia, porządek, obcięcie,
  oraz trasa znacznika zachowania.
- `terminal-news`: zakładka terminala, czyli co pokazuje, jak podaje opóźnienie, jak zachowuje się
  news i co mówi, gdy źródło stoi.

### Modified Capabilities

- `social-data-api`: „Kontrakt wyłącznie czyta” dostaje jeden wyjątek, czyli znacznik zachowania
  newsa, i nic więcej.
- `social-data-liveness`: pakiet ma drugą pętlę. Wymóg publikowania wieku ukończonego przebiegu
  obejmuje każdą pętlę, a nie tylko zbiór postów.

Pocket nie wnosi zdolności, jak przy `social-data-collects-the-posts`: jego ekrany nigdy ich nie
miały, a praca nad nim jest w `tasks.md`. `social-data-caller-access` obejmuje nowe trasy bez
zmiany wymagań: to ta sama powierzchnia REST i ci sami wołający.

## Impact

- **Workbench / `social_data`**: nowa migracja (tabele newsów i stan źródeł), dostawca RSS, lista
  źródeł, pętla newsów, trasy `news`, modele kontraktu, druga heartbeat w `serving`. Ustawienia
  z przedrostkiem `SOCIAL_NEWS_`.
- **Terminal**: `contract:generate` (ten sam plik), `src/news/`, wpis w `src/app/tabs.ts`.
  Backend ten sam co Social, więc bez nowego endpointu i bez nowego scope'u.
- **Pocket**: `contract:generate`, `src/news/`, czwarta zakładka w `tabs.ts`, `TabBar.tsx`
  i `App.tsx`.
- **Baza**: kilka tysięcy wierszy na dobę w `social`, z sufitem wyznaczonym przez 28 dni retencji. Koszt zapytań przez `db-cost-check`
  przed merge.
- **Infra i operator**: nic. Istniejący alert `social_data.loop_passes_late` czyta wymiar `loop`,
  więc nowa pętla wchodzi pod niego bez `apply`.
- **Pominięte artefakty:** żadne. `design.md` jest potrzebny, bo pomiar opóźnienia i rytm pętli to
  decyzje, a nie mechanika. `review.md` powstaje po implementacji, jak zawsze.
