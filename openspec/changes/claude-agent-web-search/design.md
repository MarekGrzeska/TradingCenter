## Context

Agent ma dziś zakaz sieci w trzech miejscach: `agent/.claude/settings.json` (`deny`), `tests/test_render.py` (`NEVER`)
i wymaganie `claude-agent-access`. Kontener już ma wyjście do internetu (sieć `claude-agent`, zwykły bridge), więc
zmiana jest w uprawnieniach i instrukcjach, nie w infrastrukturze. `WebSearch` wykonuje się po stronie Anthropic na
subskrypcji; `WebFetch` pobiera stronę z kontenera.

## Goals / Non-Goals

**Goals:** wyszukiwanie i pobieranie stron jak w Claude Code operatora przy biurku, bez listy domen.

**Non-Goals:** lista dozwolonych domen (operator jej nie chce prowadzić); przełącznik wdrożenia dla sieci (sieć jest
zawsze włączona, jak przy biurku); zmiany w przełącznikach zapisu na rachunku.

## Decisions

**D1. Reguły bez zakresu.** `WebSearch` i `WebFetch` w `allow`, usunięte z `deny`. `render.py` się nie zmienia — przenosi
z obrazu wszystko poza narzędziami rachunku. *Odrzucone:* `WebFetch(domain:…)` z ustawienia — wymaga listy, której
operator nie chce prowadzić.

**D2. Granica wstrzyknięcia w instrukcjach i w przełącznikach, nie w sieci.** Treść z sieci to dane; zapis na rachunku
i narzędzia zespołów tylko na prośbę operatora w tej samej rozmowie. Twardą granicą zostają przełączniki
`AGENT_ACCOUNT_WRITES` i `AGENT_LIVE_ACCOUNT_WRITES` (9 listopada: demo `off`, konto realne `on`) oraz strażnik `LIVE_ORDER_LIMITS`.

**D3. Zapis tylko do `out/`, ścieżką bezwzględną.** `Edit(//home/agent/work/out/**)` w `allow` (reguła `Edit` obejmuje
każde narzędzie zapisu plików); zakazy wprost dla `.claude/`, `CLAUDE.md`, `.mcp.json`, `owner-channel.md` w katalogu
roboczym i dla `~/.claude/`. Gołe `Edit`/`Write` znikają z `deny`, bo zakaz wygrywa z każdą zgodą; w trybie `dontAsk`
wszystko spoza `allow` i tak jest odrzucone. *Odrzucone:* ścieżka względna `./out/**` — zależy od katalogu startu sesji.
Wysyłka pliku idzie narzędziem `reply` kanału Telegram (`files`), które pisze tylko do czatów z `allowFrom`.

## Risks / Trade-offs

- [Zapis w tym, co sesja czyta, poszerzyłby jej uprawnienia (`settings.local.json`)] → zakaz wprost, test; entrypoint i
  tak odtwarza `.claude/` z obrazu przy każdym starcie.

- [Wyciek przez adres: wstrzyknięta strona każe pobrać URL z pozycjami albo strategią w parametrach] → agent nie ma
  sekretów systemu ani dostępu do plików tokenu; wyciec może to, co czytają narzędzia `tc-*` (pozycje, strategie,
  zespoły). Akceptowane przez operatora jak przy biurku; instrukcja zabrania wysyłania danych systemu w adresach.
- [Wstrzyknięcie każe uruchomić albo zaplanować zespół — koszt modeli] → narzędzia zespołów tylko na prośbę operatora;
  limity kosztu zespołów (`daily_limit`) ograniczają szkodę.
- [Zapis na koncie realnym jest włączony (`AGENT_LIVE_ACCOUNT_WRITES=on`) przy otwartej sieci] → strona może próbować
  nakłonić agenta do zlecenia; granicą jest wymóg „KONTO REALNE” i jawnego „tak” operatora w rozmowie oraz
  `LIVE_ORDER_LIMITS` (US100 do 1.0) w bramie; operator może wyłączyć przełącznik bez zmiany kodu. Przy włączaniu
  `AGENT_ACCOUNT_WRITES` operator decyduje świadomie, zapis wymaga potwierdzenia w rozmowie, demo i realne mają osobne przełączniki.
- [Zużycie subskrypcji przez długie wyszukiwania] → przegląd zużycia po tygodniu, jak przy wdrożeniu agenta.
