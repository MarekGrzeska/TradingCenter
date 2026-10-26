## Context

Sześć pakietów workbencha ma żywe `/…/mcp` (sesja startuje w ich `serving`), zamknięte dwiema rzeczami: Caddy odpowiada
404 (`no_tool_surface`), a `TOOL_CALLER_APPLICATION_IDS` jest pusty. Strategie i narzędzia zespołów mają serwer FastMCP
bez transportu. trading-mcp siedzi tylko w sieci `services`, z `EdgeConfig(verifier=None)`. Osoba jest już sprawdzana
tak, jak trzeba: `EdgeAuth` weryfikuje token, `RolePolicy` wpuszcza na `/mcp` tylko `admin`.

## Goals / Non-Goals

**Goals:** jedna droga z Claude Code operatora do każdej powierzchni narzędziowej produkcji, z tą samą osobą, rolą i
wyliczoną aplikacją co reszta systemu; kod, testy i Terraform gotowe do merge.

**Non-Goals:** natywny OAuth klienta MCP (metadane RFC 9728 na serwerze); narzędzia samej rozmowy (wykres, rysunki);
ślad zleceń z zewnątrz w bazie; `terraform apply`, merge i wdrożenie.

## Decisions

### D1. Token z `headersHelper`, z własnej rejestracji Entra

Claude Code uruchamia helper przy każdym połączeniu i po 401/403; helper (`scripts/mcp_token.py`, MSAL) wypisuje
`Authorization`. Rejestracja `app-tradingcenter-claude-code` jest klientem publicznym z przekierowaniem
`http://localhost`, pre-autoryzowanym na scope'ach workbencha i bramy, więc logowanie nie pyta o zgodę, a token
odświeżania jednego API daje cichy token drugiego.

*Odrzucone:* natywny OAuth Claude Code (`oauth.clientId`) — Entra nie ma DCR, a v2 odrzuca parametr `resource`, który
klient wysyła (AADSTS9010010, anthropics/claude-code#52871); `az` — działa bez Terraform, ale otwierałby każdą powierzchnię
narzędziową klientowi, który już otwiera Telegram, i log nie odróżniłby jednego od drugiego.

Helper ma 10 s limitu i nie jest cache'owany przez klienta: komenda `headers` jest tylko cicha, `login` jest osobna.

### D2. trading-mcp pod `/trading` na hoście API, z audiencją bramy

`handle_path /trading/*` w bloku `API_HOST` → `trading-mcp:80`. Bez nowego hosta, DNS i certyfikatu. Audiencja bramy, nie
workbencha: prawo do ruszania rachunku to `admin` na API bramy, to samo, którego terminal potrzebuje do rachunku; token
workbencha nie otwiera handlu.

*Odrzucone:* osobny host (`TRADING_HOST`) — DNS, certyfikat i zmienna środowiska za nic; pośrednik w workbenchu — nowa
powierzchnia w procesie, który dziś trading-mcp tylko woła.

### D3. Wyliczona aplikacja w `EdgeConfig.token_applications`

`EdgeAuth` już wyciąga aplikację z tokenu; pole `token_applications` (domyślnie `None` = bez ograniczenia) odmawia 403
tokenowi od aplikacji spoza listy, przed sprawdzeniem roli. Workbench go nie używa — tam listy trzyma `CallerAccess`
każdego pakietu; trading-mcp nie ma `CallerAccess` i dostaje listę tu. Test raz, w `packages/tc-entra-auth`.

*Odrzucone:* lista w `RequireCallerIdentity` (`tc-mcp-kit`) — czytałaby nagłówek, który `EdgeAuth` dopiero co napisał,
czyli drugi raz to samo, w drugim pakiecie.

### D4. Ślad zapisu z zewnątrz w logu trading-mcp

trading-mcp nie ma bazy; ślad to wpis przed wysłaniem i wpis ze skutkiem. Wołający czytany z żądania bieżącego
wywołania (`request_ctx` niskopoziomowego serwera MCP), nie ze zmiennej kontekstowej ustawionej wokół żądania — w
stanowym streamable-http narzędzie wykonuje się w zadaniu sesji, nie żądania. Wpisuje się każdy zapis, także
workbencha (aplikacja `tc-internal`); to nadzbiór tego, czego wymaga spec.

*Odrzucone:* baza dla trading-mcp — nowy schemat, rola i migracja dla jednego wpisu; tylko odczyty na zewnątrz —
osobny serwer z podzbiorem narzędzi, więcej kodu niż ślad, a konto jest demo i klient pyta przed każdym zapisem.

### D5. Narzędzia zespołów: podklasa FastMCP, która ustawia osobę na czas wywołania

Montaż `/team-tools` musi powstać przy imporcie, a serwer narzędzi zespołów buduje się w lifespanie — montowany jest więc
forwarder czytający serwer ze stanu. Osobę ustawia `call_tool` podklasy FastMCP (`carrying(principal)`), czytając
`X-MS-CLIENT-PRINCIPAL-ID` z żądania bieżącego wywołania — nagłówek pisze `EdgeAuth` po weryfikacji tokenu, a każdy
przysłany przez klienta wcześniej usuwa. Bez warstwy uwierzytelniającej (lokalnie) osoby nie ma, jak w rozmowie.

*Odrzucone:* `carrying()` w middleware wokół żądania — nie dociera do zadania sesji (to samo co w D4).

### D6. Strategie montowane jak pozostałe pakiety

Odwraca D7 zmiany `a-strategy-from-a-description`, której jedynym powodem był brak klienta MCP. Zespoły dalej dostają
tylko trzy narzędzia przez swój rejestr; sieć dostaje cały zestaw, z tymi samymi odmowami i licznikiem.

## Risks / Trade-offs

- [Pętla klienta nie ma sufitu tury rozmowy] → koszt wywołania dla bazy jest ten sam co z rozmowy; `prod-health` po
  tygodniu.
- [Ślad w logu rotuje (5 × 10 MB)] → transkrypt Claude Code jest drugim śladem; baza, gdyby okazało się mało.
- [Deploy zrywa sesje MCP] → klient łączy się ponownie (`/mcp` → reconnect).
- [Kolejność wdrożenia] → `terraform apply`, potem `CLAUDE_CODE_APPLICATION_ID` w środowisku `vps`, potem merge;
  `env.required` zatrzymuje deploy, gdy brakuje zmiennej.

## Migration Plan

1. `terraform apply` (operator) — nowa rejestracja i pre-autoryzacje.
2. `deploy/scripts/fill-github-environment.sh` albo ręcznie `CLAUDE_CODE_APPLICATION_ID` w środowisku `vps`.
3. Merge → deploy. Wycofanie: usunięcie pre-autoryzacji (albo całej rejestracji) w Entra zamyka drogę bez zmiany
   obrazu — helper nie dostanie tokenu; pełne — revert i przywrócenie poprzednich obrazów przez `deploy.sh`.
4. U operatora: `scripts/mcp_token.py login`, `scripts/claude-mcp.sh install`.
