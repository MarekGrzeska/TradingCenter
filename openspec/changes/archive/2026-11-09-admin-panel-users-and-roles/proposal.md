## Why

Dziś do aplikacji wchodzi każdy, kto ma konto w tenancie Entra i token dla rejestracji workbencha — a w
tenancie jest tylko operator. Nie ma sposobu, żeby kogoś zaprosić, i nie ma różnicy między „operator" a „ktoś,
kto ma tylko czytać". Chcemy zapraszać osoby po samym adresie e-mail i dawać im węższy dostęp: telefon
(pocket) w trybie tylko do odczytu, bez agenta i bez terminala.

## What Changes

- **Zaproszenia:** nowa zakładka **Użytkownicy** w terminalu. Operator wpisuje e-mail; terminal woła Microsoft
  Graph (`POST /invitations`) **tokenem zalogowanego admina** (uprawnienia delegowane `User.Invite.All`,
  `AppRoleAssignment.ReadWrite.All`, zgoda administratora w Terraform). Zaproszony zostaje gościem Entra B2B —
  może to być dowolny adres, nie tylko konto Microsoft (hasło dla konta Microsoft, jednorazowy kod e-mail dla
  reszty). Serwer nie dostaje żadnego sekretu z prawem zapisu do katalogu.
- **Role:** dwie role aplikacyjne Entra na rejestracjach workbencha i gatewaya: `admin` (pełny dostęp jak dziś)
  i `viewer` (tylko pocket, tylko odczyt, bez agenta). Rola jedzie w claimie `roles` tokenu osoby.
  Obecni użytkownicy dostają `admin` — przypisanie robi Terraform, żeby merge niczego nie odciął.
- **Egzekwowanie na serwerze, fail-closed:** drzwi (`tc-entra-auth`) czytają `roles` i przekazują je dalej;
  workbench i gateway odmawiają osobie bez roli, a `viewer` przepuszczają wyłącznie na `GET` pod `/social`
  i `/polymarket`. Czat, teams, `/market`, `/telegram`, `/alerts` i gateway — 403. To jedyny sposób, żeby
  agent (który ma narzędzia konta przez trading-mcp) nie stał się tylnymi drzwiami do handlu.
- **Terminal:** osoba bez roli `admin` widzi ekran „brak dostępu" zamiast aplikacji.
- **Pocket:** dla `viewera` znika zakładka Agent oraz każda akcja zapisu (śledzenie, usuwanie, przenoszenie
  eventów, grupy, „keep" w newsach).
- Terraform `apply` zostaje po stronie operatora (nie CI).

## Capabilities

### New Capabilities
- `access-roles`: role `admin` i `viewer`, claim `roles`, brak roli = brak dostępu, polityka tras dla `viewera`
  w workbenchu i gatewayu.
- `terminal-users`: zakładka Użytkownicy — zaproszenie po e-mailu, lista, zmiana roli, odebranie dostępu.
- `pocket-access`: pocket pokazuje `viewerowi` tylko odczyt i bez agenta.

### Modified Capabilities
- `terminal-identity`: terminal po zalogowaniu osoby bez roli `admin` pokazuje ekran braku dostępu, a nie błędy
  źródeł danych.

## Impact

- `infra/**` (Entra: `app_role` w module `easy-auth-app`, uprawnienia delegowane terminala, przypisanie `admin`)
  — stąd zmiana OpenSpec.
- `packages/tc-entra-auth` (odczyt `roles`, nowy nagłówek tożsamości osoby), `modules/workbench`
  (bramka ról nad `RootCallers` i pakietami), `modules/capital-gateway` (ta sama bramka, rola `admin`).
- `modules/terminal` (Graph, zakładka, ekran braku dostępu), `modules/pocket` (ukrywanie akcji i zakładki).
- Zasada „jeden proces na granicę bezpieczeństwa" **nie** jest ruszana: żaden proces nie dostaje zapisu do
  katalogu. Zmiana roli widoczna jest po odświeżeniu tokenu (do ~1 h) — świadomy koszt wariantu z rolami Entra.
- Przeglądu (`review.md`) nie pomijam: dotyka autoryzacji.
