## Context

Zob. `proposal.md` — Why. Cztery poprawki, każda oddzielna w Terraformie i w kodzie, ale
odkryte razem i warte wdrożenia razem. `infra/monitoring.tf` ma już wzorzec dla trzech z
nich (`azurerm_monitor_metric_alert` na `Microsoft.Web/sites`, taki sam kształt co
`alert-gateway-http-5xx`); czwarta (wyjątki) potrzebuje reguły zapytania zaplanowanego,
której w tym pliku jeszcze nie ma.

## Goals / Non-Goals

**Goals:**
- Odróżnić z zewnątrz martwy kontener market-data od zdrowego, bezczynnego.
- Alarm na 5xx i na wyjątki, symetryczny do tego, co gateway już ma albo powinien mieć.
- `AppRequests` zaczyna się w ogóle napełniać — dziś nie ma go wcale, więc żaden przyszły
  alert oparty na żądaniach (ten, i każdy kolejny) nie miałby na czym stanąć.

**Non-Goals:**
- Sonda dostępności dla gateway. Nie jest publicznie osiągalna
  (`ip_restriction_default_action = "Deny"` w `infra/app-service.tf`, dozwolone tylko
  adresy market-data) — zewnętrzny test URL nie dotrze do niej niezależnie od
  uwierzytelnienia, więc nie ma czego testować z zewnątrz.
- Głęboki healthcheck (baza, stan ingestu) pod trasą dostępności. To już robi istniejąca
  `GET /health` (`market_data/routers/meta.py`) dla uwierzytelnionego wywołania — odkryta
  dopiero przy implementacji, stąd nowa trasa nazywa się `/ping`, nie `/health`. Trasa
  dostępności ma dowodzić czegoś węższego, patrz Decisions.
- Strojenie progu alertu na wyjątki w locie. Liczba w tej zmianie jest oszacowaniem z
  zebranych danych, nie wynikiem eksperymentu — nazwane wprost jako coś do obserwacji.

## Decisions

**Trasa dostępności nie sprawdza zależności, tylko odpowiada.** Rozważano healthcheck,
który pyta bazę i bramkę, zanim odpowie 200 — odrzucone, bo zlewa dwa różne pytania w
jedno. „Czy proces żyje" i „czy jego zależności są zdrowe" mają już osobne kanały: to
pierwsze nic dotąd nie miało, to drugie ma `collection_state`
(`market-data-tracking`) i alert na wiek świecy. Sonda, która odpowiada 5xx, bo baza jest
przez chwilę wolna, zamieniłaby dostępność w trzecią, gorszą kopię tego samego sygnału —
i to akurat wtedy, gdy jedyne, co jest zepsute, ma już swój alarm.

**Trasa dostępności jest wyłączona z Easy Auth, tak jak `/ws/candles`, nie chroniona
osobnym sekretem.** Alternatywa — token albo klucz w query string dla samego pinga — była
rozważana i odrzucona: sonda dostępności z definicji nie ma nic do ukrycia (patrz wymaganie
w delcie specyfikacji: żadnych danych archiwum w odpowiedzi), więc sekret chroniłby pustą
odpowiedź i tylko dokładałby kolejne miejsce, gdzie osobny operator musiałby pamiętać o
rotacji.

**Próg alertu na wyjątki: 15 na okno 15 minut, licząc `AppExceptions`.** Zmierzony szum
`ConnectionClosedError` (przełączenia WebSocketa bramki) to 736 wystąpień na 30h, czyli
~24,5/h ≈ ~6,1 na 15 minut — to musi zostać poniżej progu. Zmierzona prawdziwa awaria
(45× `UndefinedColumnError` w 23 minuty, 10 sierpnia) to ~29 na 15-minutowe okno w tym
samym tempie — to musi zostać powyżej progu. 15 leży niemal dokładnie pomiędzy, ze
współczynnikiem ~2,4× nad szumem i ~2× pod zmierzoną awarią. To oszacowanie z dwóch
punktów danych, nie prawo natury — nazwane w Open Questions.

**`telemetry.configure()` przenosi się przed `from fastapi import FastAPI`, nie tylko przed
`app = FastAPI(...)`, w obu modułach osobno.** Przyczyna: `opentelemetry-instrumentation-
fastapi` włącza się przez podmianę **atrybutu** `fastapi.FastAPI` na podklasę, która
instrumentuje samą siebie w `__init__` (`_InstrumentedFastAPI` w
`opentelemetry/instrumentation/fastapi/__init__.py`, `FastAPIInstrumentor._instrument()`).
Pierwsza wersja tej zmiany przenosiła wywołanie tylko tuż przed `app = FastAPI(...)` —
zweryfikowane w trakcie implementacji jako niewystarczające: `from fastapi import FastAPI`
na górze pliku już wcześniej związał nazwę `FastAPI` w przestrzeni nazw modułu z tym, co
atrybut trzymał w chwili wykonania tej instrukcji, i żadne późniejsze wywołanie tego nie
cofa — podmiana atrybutu na module `fastapi` nie przepisuje nazw, które inne moduły już
z niego wyciągnęły. Sprawdzone bezpośrednio: `app._is_instrumented_by_opentelemetry` był
`False`/nieobecny przy poprzedniej kolejności i `True` po przeniesieniu importu `FastAPI`
(wraz z importem `Request` w tej samej instrukcji) pod wywołanie `configure()`. Rozważana
alternatywa: jawne `FastAPIInstrumentor.instrument_app(app)` zaraz po utworzeniu `app`,
zamiast przenoszenia importu — odrzucona jako dodatkowy, osobny krok robiący to samo, co
sama zmiana kolejności importu robi za darmo. Bez biblioteki współdzielonej między
modułami (`docs/architecture.md`, „Why no shared library") — dwie osobne poprawki, nie
jedna.

**Alert na zanik ruchu tylko dla market-data, nie dla gateway.** Gateway jest ip-restricted
do adresów market-data — brak żądań z zewnątrz jest tam stanem normalnym, nie sygnałem.
Jeśliby kiedyś market-data przestało wołać gateway, `alert-market-data-http-requests-low`
(nowy, z tej zmiany) zauważy to pośrednio: market-data samo przestanie odpowiadać, bo jego
własne trasy zależą od bramki.

## Risks / Trade-offs

**Trasa dostępności jest publiczna i nieuwierzytelniona.** → Świadome i ograniczone
wymaganiem w delcie specyfikacji: odpowiedź nie niesie nic poza faktem, że proces żyje.
Nowa powierzchnia ataku jest węższa niż dotychczasowa: sama odpowiedź nie zależy od
niczego, czym dałoby się manipulować.

**Test dostępności Azure kosztuje coś, choćby drobne, na subskrypcji, która celuje w
darmowy poziom.** → `azurerm_application_insights_standard_web_test` w najtańszym wariancie
(jedna lokalizacja, częstotliwość rzadsza niż domyślna) mieści się w typowym darmowym
grancie; do potwierdzenia przy `terraform apply` przez operatora, nie zgadywane tutaj.

**Przeniesienie `telemetry.configure()` zmienia moment, w którym proces zaczyna logować i
łączyć się z Application Insights — teraz przy imporcie modułu, nie przy starcie ASGI.** →
`configure_logging()` jest no-opem, gdy root logger ma już handler, więc powtórny import w
tym samym procesie nic nie psuje; testy importujące `app` bez uruchamiania `lifespan()` po
prostu skonfigurują logging wcześniej niż dziś, co jest efektem ubocznym bez znaczenia
funkcjonalnego — potwierdzone uruchomieniem pełnego zestawu testów obu modułów w ramach tej
zmiany.

**Próg wyjątków może okazać się zbyt czuły albo zbyt tępy — dane są z jednej nocy.** →
Nazwane wprost w Open Questions; tania poprawka po fakcie, nie powód, by nie zakładać
reguły teraz.

## Migration Plan

1. Kod: nowa trasa `/ping` w market-data, przeniesienie `telemetry.configure()` w obu
   modułach. Bez migracji bazy, bez zmiany kontraktu HTTP poza jedną nową trasą.
2. Terraform: trzy nowe `azurerm_monitor_metric_alert`/regułę zapytania plus test
   dostępności i wpis w `excluded_paths`. Pisane w tej zmianie, `terraform apply` — operator,
   lokalnie, nigdy CI.
3. Wdrożyć oba moduły przed `terraform apply`, tak jak przy alarmie wieku świecy: reguła 5xx
   i alert ruchu odwołują się do istniejących zasobów App Service, więc kolejność nie jest
   tu twarda w tę stronę — ale test dostępności odpytujący `/ping` zanim ta trasa istnieje
   zgłosiłby fałszywy alarm od pierwszej minuty. Moduł najpierw.
4. Potwierdzić w Application Insights, że `AppRequests` ma punkty po wdrożeniu — to jest
   dowód, że przeniesienie `configure()` faktycznie zadziałało, nie tylko że kod się
   skompilował.

Wycofanie: `terraform apply` poprzedniej rewizji `monitoring.tf` i `app-service.tf` zdejmuje
nowe reguły i wpis `excluded_paths`. Kod modułów nie wymaga wycofania — nowa trasa i
wcześniejsze `configure()` nikomu nie przeszkadzają, jeśli Terraform ich nie używa.

## Open Questions

- Próg 15/15min na `AppExceptions` jest oszacowaniem z jednej nocy pomiarów. Warto wrócić
  do niego po pierwszym tygodniu produkcji i porównać z rozkładem, który się faktycznie
  ustabilizuje — nie zmienia to specyfikacji ani zadań, tylko samą liczbę w Terraformie.
