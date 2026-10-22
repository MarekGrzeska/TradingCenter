## Verdict

Zaimplementowane w kodzie i infrastrukturze jako plik Terraform; **nie wdrożone**. Bramka ról (`tc-entra-auth`) działa w workbenchu
i gatewayu, terminal ma ekran braku dostępu i zakładkę Użytkownicy, pocket ma tryb `viewer`. Świadomie niedokończone: `terraform apply`
(zadanie operatora), sprawdzenie ustawień zaproszeń gości w tenancie oraz próba na prawdziwym koncie `viewera` po wdrożeniu —
wszystko to wymaga prawdziwego tenanta, którego testy nie widzą. Nie pomylić z przeoczeniem: zakładka Użytkownicy nie ma testu
przeciwko prawdziwemu Graph (tylko przeciwko atrapie `fetch`), więc zakresy i kształty odpowiedzi Graph są zweryfikowane z dokumentacji,
nie z wywołania.

## Verified

- `packages/tc-entra-auth`: `uv run pytest` → 57 passed; `ruff check` czysty; `pyright` 0 errors.
- `modules/workbench`: `uv run pytest` (cały zestaw) → 2906 passed, 11 skipped; `ruff check`, `pyright workbench tests/test_roles.py` czyste.
- `modules/capital-gateway`: `tests/test_server_mode.py` → 18 passed; `ruff`/`pyright` czyste. `modules/trading-mcp`: 103 passed (korzysta z tego samego `EdgeConfig`, bez polityki).
- `modules/terminal`: `pnpm test` → 935 passed (78 plików), `pnpm lint`, `pnpm typecheck` czyste, `pnpm contract:check` → „Every contract is up to date".
- `modules/pocket`: `pnpm test` → 112 passed, `lint`, `typecheck` czyste, `contract:check` → „The contract is up to date."
- `infra`: `terraform fmt -recursive` i `terraform validate` → Success. **Nie uruchomiono `plan` ani `apply`.**
- `scripts/tests/test_guide_ceiling.py` → 4 passed (CLAUDE.md ok, 18 912 znaków).

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | wdrożenie | Merge przed `terraform apply` odcina operatora: bramka jest fail-closed, a jego token nie niesie `roles`. | Opisane w CLAUDE.md, design.md i zadaniu 6.2; kolejność jest po stronie operatora |
| Medium | `packages/tc-entra-auth/tc_entra_auth/roles.py` | `/me` zwraca także role nieznane (np. `owner`), nie tylko `admin`/`viewer`; bramka je ignoruje, więc to kosmetyka. | Akceptowane |
| Medium | `modules/terminal/src/users/usersApi.ts` | `setRole` to kilka wywołań Graph bez transakcji; przerwa po środku zostawia osobę z niepełnym zestawem. Kolejność (najpierw dodaj, potem usuń) sprawia, że błąd daje nadmiar, nie blokadę. | Akceptowane, opisane w kodzie |
| Low | `modules/terminal/src/access/AccessGate.tsx` | Gdy `/me` nie odpowiada, terminal renderuje się jak dotąd (serwer i tak odmawia). Wybór: nie zamykać operatora przed ekranem pokazującym awarię. | Świadome |
| Low | pocket `useRole` | Gdy `/me` nie odpowiada, pocket pokazuje węższy ekran `viewer`. | Świadome |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| access-roles: Rola z tokenu — Klient podaje własną rolę | `packages/tc-entra-auth/tests/test_roles.py::test_the_roles_the_process_sees_are_the_tokens_not_the_clients`, `::test_a_client_header_does_not_survive_on_a_path_without_proof` |
| access-roles: Rola z tokenu — Wywołanie wewnętrzne kluczem | `test_roles.py::test_a_service_key_is_internal_and_not_held_to_the_viewer_policy` |
| access-roles: Brak roli — Gość bez roli; Token sprzed nadania roli | `test_roles.py::test_no_usable_role_is_refused_everywhere_but_me`; `modules/workbench/tests/test_roles.py::test_a_person_with_no_role_reaches_nothing_but_me` (token bez claimu `roles` to ten sam przypadek) |
| access-roles: Admin ma dostęp jak dotychczas | `test_roles.py::test_an_admin_reaches_everything`; `modules/workbench/tests/test_server_mode.py::test_the_terminal_with_a_token_reaches_the_root` |
| access-roles: Viewer — czyta posty / zapis / agent | `modules/workbench/tests/test_roles.py::test_a_viewer_reaches_the_two_archives_for_reading_and_no_other_door` (w tym `PUT /social/news/keep`, `DELETE /polymarket/events/x`, `/sessions`, `*/mcp`) |
| access-roles: Viewer prosi gateway o token terminala | `modules/capital-gateway/tests/test_server_mode.py::test_a_person_who_is_not_an_admin_does_not_reach_the_account[viewer]` |
| access-roles: `GET /me` — viewer / bez roli | `modules/workbench/tests/test_roles.py::test_me_says_what_the_door_wrote_and_admin_where_there_is_no_door` |
| access-roles: Praca lokalna bez tokenów | `packages/tc-entra-auth/tests/test_roles.py::test_without_a_policy_the_token_alone_decides`; `test_me_says_what_the_door_wrote_and_admin_where_there_is_no_door` |
| terminal-users: Admin otwiera zakładkę | `modules/terminal/src/users/UsersView.test.tsx` (lista osób z rolami); zakres Graph — **gap** (patrz niżej) |
| terminal-users: Zaproszenie viewera / admina | `usersApi.test.ts::inviting › gives an admin the role on both APIs and a viewer the workbench one only`, `::sends a viewer to the pocket from the e-mail`; `UsersView.test.tsx::lists who has access and invites an address as a viewer` |
| terminal-users: Zły adres | `UsersView.test.tsx::does not call the directory for something that is not an address` |
| terminal-users: Awans viewera; Odebranie dostępu | `usersApi.test.ts::changing a role › promotes a viewer…`, `::takes every assignment away on revoke` |
| terminal-users: Ostatni admin | `usersApi.test.ts::guards`, `UsersView.test.tsx::refuses to take the admin role from the signed-in admin` |
| terminal-identity: Viewer otwiera terminal | `modules/terminal/src/access/AccessGate.test.tsx::shows a viewer a page that says so, and none of the terminal` |
| terminal-identity: Praca lokalna | `modules/terminal/src/App.test.tsx` oraz reszta pakietu bez tożsamości (gate `unconfigured` → dzieci); osobnego testu bramki z `unconfigured` brak — **gap** |
| pocket-access: Viewer otwiera pocket | `modules/pocket/src/access/viewer.test.tsx` (ekrany bez akcji zapisu), `app/tabs.test.ts::offers a viewer the archive and not the agent…` |
| pocket-access: Zapamiętana zakładka Agent | `app/tabs.test.ts::offers a viewer the archive and not the agent, and moves a remembered agent tab off it` |
| pocket-access: Admin w pocket | `viewer.test.tsx::useRole › reads ["admin"] as admin`; istniejące testy ekranów bez `readOnly` |
| pocket-access: Gość bez roli | `viewer.test.tsx::useRole › reads [] as none`; sam `NoAccessScreen` nie ma testu renderu — **gap** |

## Gaps

- Zakładka Użytkownicy nie była uruchomiona przeciwko prawdziwemu Graph: zakresy (`User.Invite.All`, `User.Read.All`,
  `AppRoleAssignment.ReadWrite.All`), `.default` i kształt `appRoleAssignedTo` wynikają z dokumentacji Microsoftu.
  Do sprawdzenia przy pierwszym użyciu po `apply`.
- Brak testu renderu `NoAccessScreen` w pocket i testu `AccessGate` w trybie `unconfigured` w terminalu.
- Zadania 1.5 (`apply`), 6.1 (ustawienia zaproszeń gości w tenancie), 6.2 (kolejność wdrożenia i próba na prawdziwym koncie)
  zostają po stronie operatora.
- Zmienne GitHub `ACCESS_*` (ustawia `fill-github-environment.sh` albo operator ręcznie po `apply`) — bez nich zakładka mówi, że nie jest skonfigurowana.
