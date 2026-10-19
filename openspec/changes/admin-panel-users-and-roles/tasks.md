## 1. Entra (infra) — wdrożenie PRZED kodem

- [x] 1.1 `easy-auth-app`: zmienna `app_roles` (`admin`, `viewer`; `allowed_member_types = ["User"]`), stałe GUID-y przez `random_uuid`
- [x] 1.2 Role na rejestracji workbencha (`admin`, `viewer`) i gatewaya (`admin`)
- [x] 1.3 `admin_user_object_ids` + `azuread_app_role_assignment` dla obecnych użytkowników na obu rejestracjach
- [x] 1.4 Terminal: `required_resource_access` na Microsoft Graph (delegowane) + `azuread_service_principal_delegated_permission_grant` (AllPrincipals)
- [ ] 1.5 `terraform fmt`/`validate` zrobione; plan w PR, `apply` robi operator, potem odnawia token i sprawdza `roles`

## 2. tc-entra-auth

- [x] 2.1 `EdgeAuth`: odczyt `roles`, zdejmowanie przychodzącego `X-TC-Roles`, zapis własnego (`internal` dla klucza)
- [x] 2.2 `RoleGate`: polityka z danych (prefiksy dla `viewera`), brak ról → 403, `/me` i `/health` wyjątkami
- [x] 2.3 Testy pakietu: podrobiony nagłówek, brak claimu, viewer GET/POST, internal, tryb bez tokenów

## 3. workbench i gateway

- [x] 3.1 Workbench: `RoleGate` pod `EdgeAuth`, `GET /me`, polityka `/social` + `/polymarket`
- [x] 3.2 Gateway: `RoleGate`, tylko `admin`/`internal`
- [x] 3.3 Test układu: każdy `GET` pod `/social` i `/polymarket` jest odczytem; nowy pakiet zamknięty dla `viewera`
- [x] 3.4 Test: `viewer` dostaje 403 na czacie, teams, `/market`, `/telegram`, `/alerts`, `*/mcp`
- [x] 3.5 Kontrakty: `contract:check` terminala i pocket po dodaniu `/me`

## 4. terminal

- [x] 4.1 Ekran braku dostępu po `GET /me` (viewer / brak roli), bez wołania innych tras
- [x] 4.2 Klient Graph (token z zakresem proszonym przy wejściu na zakładkę, osobny od tokenów modułów)
- [x] 4.3 Zakładka Użytkownicy: lista, zaproszenie (walidacja e-mail, rola), zmiana roli, odebranie dostępu
- [x] 4.4 Zabezpieczenia: brak usunięcia ostatniego admina i własnej roli; komunikat o odnowieniu tokenu
- [x] 4.5 Testy: happy path, jedna odmowa, ostatni admin (zasada trzech testów widoku)

## 5. pocket

- [x] 5.1 `GET /me` po zalogowaniu; ekran braku dostępu dla pustej listy ról
- [x] 5.2 `viewer`: bez zakładki Agent, zapamiętana zakładka wraca do dozwolonej
- [x] 5.3 `viewer`: ukryte śledzenie/usuwanie/przenoszenie eventów, grupy i „keep"
- [x] 5.4 Testy zakładek i ukrytych akcji

## 6. Wdrożenie i dokumenty

- [ ] 6.1 Zweryfikować ustawienia współpracy zewnętrznej tenanta (zaproszenia gości, e-mail OTP)
- [ ] 6.2 Kolejność: `apply` → odnowienie tokenu → merge → `deploy-watch` → próba `viewera` na prawdziwym koncie
- [x] 6.3 `docs/architecture.md` i `modules/workbench/README.md`: rola osoby vs `caller_access`; CLAUDE.md jedną linią (bramka ról)
- [x] 6.4 `review.md` po wykonaniu zadań (autoryzacja — zasługuje na przegląd)
