## Context

Drzwi (`packages/tc-entra-auth`, `EdgeAuth`) weryfikują token Entra i zapisują jedną tożsamość *aplikacji*
(`azp`/`appid`) w `X-MS-CLIENT-PRINCIPAL`; rekordy `caller_access` każdego pakietu autoryzują aplikację, nie osobę.
Pocket i terminal to dwie aplikacje, ale ich klientem jest publiczny SPA: każdy gość tenanta może zalogować się
do rejestracji terminala i dostać token workbencha i gatewaya (pre-authorization). Dlatego sama lista aplikacji
nie odróżni `viewera` od `admina` — potrzebna jest warstwa o osobie. Motywacja: `proposal.md`.

## Goals / Non-Goals

**Goals:**
- Rola osoby egzekwowana w procesie, fail-closed, jednym mechanizmem dla workbencha i gatewaya.
- Zapraszanie i zarządzanie rolami bez sekretu z zapisem do katalogu na serwerze.
- Wdrożenie, które nie odcina operatora.

**Non-Goals:**
- Role per-pakiet, per-zasób albo edytowalne z poziomu aplikacji (są dwie, stałe).
- Własna tabela użytkowników, własne hasła, federacja Google (jednorazowy kod e-mail Entra wystarcza).
- Natychmiastowe cofnięcie roli (patrz ryzyka).

## Decisions

**1. Role jako app roles Entra, nie tabela w bazie.** Wybór użytkownika. Rola jedzie w `roles` tokenu, więc proces
nie potrzebuje bazy ani zapytania na żądanie, a źródłem prawdy jest katalog, który i tak trzyma tożsamość.
*Alternatywa:* tabela `users` w workbenchu — natychmiastowa zmiana i pełna kontrola, ale drugi system tożsamości
do utrzymania i własna ścieżka zapisu, którą trzeba chronić.

**2. Graph woła terminal tokenem admina (delegowane), nie serwer.** Zakresy `User.Invite.All`,
`AppRoleAssignment.ReadWrite.All` i `User.Read.All` (adres i stan zaproszenia osób z listy),
zgoda administratora w Terraform (`azuread_service_principal_delegated_permission_grant`). Skuteczne prawa to
przecięcie zgody i ról katalogowych zalogowanego: gość-`viewer` nie ma roli w katalogu, więc Graph go odrzuci
nawet z tokenem terminala — druga warstwa obrony. *Alternatywa:* uprawnienia aplikacyjne w sekrecie procesu —
pierwszy proces z prawem zapisu do katalogu, nowa granica bezpieczeństwa i sekret do wycieku. Odrzucona.
Konsekwencja: kolejny admin w aplikacji musi też mieć rolę katalogową (np. Application Administrator + Guest
Inviter); dziś jest jeden.

**3. Jedna bramka ról w `tc-entra-auth`, nie rozproszone sprawdzenia.** `EdgeAuth` czyta `roles`, zdejmuje
przychodzący nagłówek `X-TC-Roles` i zapisuje własny (dla klucza wewnętrznego: `internal`). Politykę (`RolePolicy`,
opcjonalna część `EdgeConfig`) stosuje ten sam `EdgeAuth` zaraz po ustaleniu tożsamości — osobny middleware wymagałby
odróżniania „serwer bez ról" od „praca lokalna" po braku nagłówka, a tu `None` znaczy jedno: brak polityki. Reguły:
brak ról → 403; `admin`/`internal` → przepuść; `viewer` → tylko `GET` pod `/social`, `/polymarket` plus `/me`,
nigdy ścieżka z segmentem `mcp`. Polityka to dane przekazane przez proces (prefiksy), nie kod w pakiecie. Bramka stoi przed `RootCallers` i przed zamontowanymi pakietami, więc jedna reguła pokrywa korzeń,
każdy pakiet i `/mcp` — nowy pakiet jest domyślnie zamknięty dla `viewera`.
*Alternatywa:* sprawdzenie w `caller_access` każdego pakietu — rekordy autoryzują aplikację, mieszanie osoby i aplikacji
w jednym miejscu to dokładnie pomyłka, przed którą CLAUDE.md ostrzega (`X-MS-CLIENT-PRINCIPAL-ID` nazywa osobę).
Bramka czyta rolę z własnego nagłówka, nie z tego.

**4. `GET /me` z serwera jako jedyne źródło dla ekranów** (role i identyfikator osoby, żeby panel nie pozwolił zabrać sobie roli). Ekrany nie dekodują tokenu; pytają workbench,
który odpowiada rolą z tej samej bramki. Dostępne dla każdego ważnego tokenu, także bez roli — inaczej ekran
nie odróżni „brak dostępu" od awarii. Lokalnie (bez bramki) odpowiada `admin`.

**5. Role na dwóch rejestracjach: workbench i gateway.** Token gatewaya nie niesie ról workbencha, a `viewer`
może go zdobyć przez rejestrację terminala. Moduł `easy-auth-app` dostaje zmienną `app_roles`; `admin` jest
przypisywany na obu rejestracjach, `viewer` tylko na workbenchu — `viewer` bez roli na gatewayu dostaje tam 403.
trading-mcp dalej widzi tylko workbench z kluczem wspólnym, więc nie ma osobnej bramki.

**6. Obecnych użytkowników przypisuje Terraform** (`admin_user_object_ids`, `azuread_app_role_assignment`); panel
robi to samo dla nowych przez Graph. `apply` zostaje operatora (reguła repo).

**7. Zaproszenie: `POST /invitations` z `inviteRedirectUrl` na pocket (viewer) lub terminal (admin)**,
potem od razu `POST /users/{id}/appRoleAssignments` dla zwróconego `invitedUser.id`. Rola przy zaproszeniu,
bo „po pierwszym logowaniu" wymagałoby procesu, który zauważy logowanie.

## Risks / Trade-offs

- **Operator odcięty po merge** → bramka jest fail-closed, a obecny token nie ma `roles`. Kolejność jest częścią
  planu: najpierw `apply` (role i przypisanie `admin` — stary kod ignoruje nieznany claim), operator odnawia token,
  sprawdza `roles` w tokenie, dopiero potem merge. Deploy nie ma jak tego sprawdzić sam; zapisano w Migration Plan.
- **Cofnięcie roli działa po odnowieniu tokenu (do ok. godziny)** → zaakceptowane (wybór wariantu 1); zakładka
  to mówi. Dla awaryjnego natychmiastowego odcięcia: usunąć gościa z tenanta — Entra unieważnia sesję.
- **Operator zablokuje sam siebie w panelu** → panel odmawia usunięcia ostatniego admina i własnej roli.
- **Tenant może blokować zaproszenia gości lub e-mail OTP** (ustawienia współpracy zewnętrznej) → zadanie
  weryfikujące; w razie blokady zmiana ustawienia leży po stronie operatora.
- **`az` operatora** (`/telegram`) niesie token użytkownika z jego rolą `admin` — bramka go przepuszcza; bez
  przypisania roli przestałby działać, co pokrywa to samo przypisanie.
- **Nowa trasa pod `/social` albo `/polymarket` z niebezpiecznym `GET`** (efekt uboczny) byłaby otwarta dla
  `viewera` → polityka opiera się o metodę, więc test w workbenchu wylicza trasy tych prefiksów i wymaga, by
  każdy `GET` był odczytem; łamanie tej konwencji wychwyci test.
