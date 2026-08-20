## 1. Ustalić punkt odniesienia

- [ ] 1.1 Zapisać zbiór nazw wymagań i scenariuszy z całego `openspec/specs/` do pliku
      roboczego (389 postawień, 356 nazw unikalnych, 1033 scenariusze)
- [ ] 1.2 Zapisać, które 33 postawienia są powtórzeniem i w których speckach stoją

## 2. Specki pakietów — przed odchudzeniem czegokolwiek

- [ ] 2.1 `tc-runtime-database-connection`: dziewięć wymagań przeniesionych z ciałem
      i scenariuszami bez zmiany znaku
- [ ] 2.2 `tc-runtime-browser-access`: wymagania wspólne dla trzech `*-browser-access`
- [ ] 2.3 `tc-mcp-kit-tool-surface`: trzy wymagania wspólne dla `market-data-tools`,
      `trading-mcp-tools`, `workbench-team-tools`
- [ ] 2.4 `openspec validate --strict` — korpus ma teraz nazwy w nadmiarze, nie w niedomiarze

## 3. Scalić bliźniaki agent/teams w workbench

- [ ] 3.1 `agent-database-connection` + `teams-database-connection` →
      `workbench-database-connection` (dwa łańcuchy, dwie bazy, dwa klucze blokady jako
      wartości jednego wymagania — patrz Open Questions w `design.md`)
- [ ] 3.2 `agent-browser-access` + `teams-browser-access` → `workbench-browser-access`
- [ ] 3.3 `agent-models` + `teams-models` → `workbench-models`
- [ ] 3.4 `agent-tool-access` + `teams-tool-access` → `workbench-tool-access`
- [ ] 3.5 `agent-usage` + `teams-usage` → `workbench-usage`

## 4. Odchudzić konsumentów do tego, co ich własne

- [ ] 4.1 `market-data-database-connection` — zostaje „Wygasające poświadczenie jest
      odnawiane" plus jedno wymaganie o sparowaniu
- [ ] 4.2 `workbench-database-connection` — zostają dwa łańcuchy i „Moduł nie dzieli bazy
      z innym modułem" plus jedno o sparowaniu
- [ ] 4.3 `market-data-browser-access`, `workbench-browser-access` — jak wyżej
- [ ] 4.4 `market-data-tools` — zostaje jedenaście narzędzi i sufit z liczbą
- [ ] 4.5 `trading-mcp-tools` — zostaje oznaczenie zapisu na czterech narzędziach
- [ ] 4.6 `workbench-team-tools` — zostaje to, co jest jego

## 5. Sprawdzić, że nic nie zginęło

- [ ] 5.1 Zbiór nazw wymagań identyczny z 1.1 — 356 nazw, ani jednej mniej, ani jednej
      nowej poza trzema speckami pakietów
- [ ] 5.2 Zbiór nazw scenariuszy identyczny z 1.1 co do znaku
- [ ] 5.3 Postawień 389 → 367; żadna nazwa nie występuje dwa razy poza tymi, dla których
      `design.md` przewiduje wymaganie o sparowaniu
- [ ] 5.4 `openspec validate --strict` na całym korpusie
- [ ] 5.5 `openspec list` — żadna zdolność nie zniknęła bez następcy

## 6. Zapisać, co się z tego dowiedzieliśmy

- [ ] 6.1 `review.md` z liczeniem przed i po
- [ ] 6.2 Reguła „pakiet dostaje speckę wtedy i tylko wtedy, gdy ma więcej niż jednego
      konsumenta" do `docs/architecture.md`, sekcja o współdzieleniu
