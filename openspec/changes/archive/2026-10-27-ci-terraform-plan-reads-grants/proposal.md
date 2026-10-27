## Why

Job `plan` w `terraform.yml` pada na każdym PR z `infra/` od 19 października 2026. Tożsamość CI ma z Microsoft Graph tylko
`Application.Read.All`, a od zmiany `admin-panel-users-and-roles` stan zawiera delegowany grant `terminal_graph`, którego
odczyt wymaga `DelegatedPermissionGrant.Read.All` (403 `Authorization_RequestDenied`). Bez ochrony gałęzi nic to nie
blokuje, ale plan w PR był bezużyteczny akurat wtedy, gdy zmiany dotykały Entra.

Drugi powód tego samego objawu: CI nie dostawał `admin_user_object_ids`, więc jego plan proponował odebranie roli `admin`
kontu Gmail operatora (`73c09587-…`). Ten sam dryf był w lokalnym `terraform.tfvars` i został tam poprawiony 27.10.

## What Changes

- `infra/github-oidc.tf`: aplikacja CI dostaje drugie uprawnienie Graph, tylko do odczytu:
  `DelegatedPermissionGrant.Read.All`. Zapisu w katalogu dalej nie ma, bo CI tylko planuje.
- `.github/workflows/terraform.yml`: `TF_VAR_admin_user_object_ids` ze zmiennej repozytorium
  `TF_VAR_ADMIN_USER_OBJECT_IDS` (lista JSON, domyślnie `[]`).

Zastosowane przez operatora 27.10: `terraform apply` dodał jedno przypisanie roli i niczego nie zniszczył; zmienna
repozytorium jest ustawiona.

## Capabilities

### New Capabilities

### Modified Capabilities

Brak: żadne wymaganie się nie zmienia, zmiana dotyczy uprawnień narzędzia CI. Dlatego `skip_specs`, a
`design.md` i `tasks.md` pominięto: dwie linie konfiguracji nie mają decyzji do zapisania ani kroków do odhaczenia.

## Impact

- `infra/github-oidc.tf`, `.github/workflows/terraform.yml`.
- Weryfikacja: job `plan` na PR z tą zmianą przechodzi i pokazuje „No changes”.
