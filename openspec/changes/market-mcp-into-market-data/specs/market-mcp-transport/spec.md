## REMOVED Requirements

### Requirement: Dwa transporty, jeden zestaw narzędzi

**Reason**: Transport stdio znika wraz z modułem. Istniał dla klienta MCP uruchamianego na
pulpicie operatora obok procesu; archiwum jest usługą z bazą danych i migracjami, więc
drugi entrypoint mówiący MCP po strumieniach procesu byłby nową drogą startu modułu
z bazą, nie zachowaniem istniejącej. Decyzja podjęta przy tej propozycji, świadomie
i z ceną nazwaną w `proposal.md`.
**Migration**: Brak zamiennika dla stdio. Klient MCP na pulpicie sięga po narzędzia tą samą
drogą co `agent` i `teams` — po sieci, pod adresem powierzchni narzędziowej, niosąc
tożsamość (`market-data-caller-access`). Wymaganie „jeden zestaw opisany raz" przenosi się
tam jako „Powierzchnia narzędziowa jest osiągalna po sieci, jedną drogą"; test parzystości
transportów odchodzi razem z drugim transportem.

### Requirement: Żądanie z sieci niesie tożsamość wołającego

**Reason**: Moduł `market-mcp` przestaje istnieć; wymóg dotyczy odtąd archiwum.
**Migration**: `market-data-caller-access`, wymaganie o tej samej nazwie, treść bez zmian.
Dołącza do niego wymaganie nowe — „Tożsamość rozstrzyga, po którą powierzchnię wolno
sięgnąć" — bo sama obecność tożsamości przestaje wystarczać, odkąd za tą samą bramą stoi
również kontrakt REST archiwum, w tym trasy zmieniające stan.

### Requirement: Zdrowie modułu da się sprawdzić bez sesji MCP

**Reason**: Jak wyżej.
**Migration**: `market-data-caller-access`, „Zdrowie modułu da się sprawdzić bez sesji MCP
i bez tożsamości". Scenariusz „sonda przy niedostępnym archiwum" znika bez zamiennika:
opisywał moduł stojący i mówiący, że archiwum leży — stan, który przestaje istnieć, gdy
sonda i archiwum są tym samym procesem. Doszedł natomiast wymóg, żeby lista tras wyjętych
spod tożsamości nie objęła nigdy trasy niosącej dane.
