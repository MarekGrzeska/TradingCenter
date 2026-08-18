## Verdict

Odmowa przy braku tożsamości operatora dostała granicę zamiast wyjątku: obowiązuje tam,
gdzie tożsamość **mogła** być wystawiona — za uwierzytelniaczem albo przy `teams` spoza tej
maszyny — a tylko gdy nie zachodzi żadne z dwojga, wywołanie idzie nie niosąc żadnej
tożsamości i `teams` przypisuje własny principal nieuwierzytelnionego żądania. Produkcja jest
po stronie odmowy na obu warunkach, odczytane z `infra/app-service.tf`, nie założone.

Świadomie niedokończone: **przebieg na uruchomionym stosie** (zadanie 5.2) — czy `list_models`
z czatu odpowiada i czy zespół założony rozmową stoi w zakładce Teams tego samego terminala.
Testy dowodzą, że wywołanie wychodzi bez nagłówka i że `teams` je przyjmie; że **ta sama
lista** je pokaże, dowiedzie tylko stos, a stos jest operatora.

Czego nie brać za przeoczenie: `optional=False` jest domyślne w `operator_token`, a jedynym
wołającym podającym cokolwiek innego jest seam narzędzi. Tak ma być — nikt nie trafia do
łagodnej gałęzi przez zapomnienie argumentu, i to jest utrwalone testem.

## Verified

W `modules/teams-mcp`, po ostatniej poprawce:

```
uv run ruff check .                      All checks passed!
uv run pyright                           0 errors, 0 warnings, 0 informations
uv run pytest -q                         82 passed (68 przed tą zmianą)
uv run python scripts/contract.py check   Contract is up to date.
```

Nie uruchamiane: `pytest -m live` (ten moduł go nie ma) i cokolwiek przeciw prawdziwemu
`teams` — cały ruch sieciowy w tych testach idzie przez `respx`.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| low | `teams_mcp/client.py:47` | `operator_identity_optional` był zwykłym atrybutem publicznym skopiowanym z ustawień. Cokolwiek trzymające klienta mogło go przestawić po walidacji startowej i poszerzyć wyłom bez zmiany konfiguracji. | **FIXED** w tym samym commicie co reszta — schowany za `property` nad `_operator_identity_optional` |
| low–med | `Dockerfile:28` + `config.py` | Obraz ustawia `TEAMS_MCP_HOST=0.0.0.0`, a `REQUIRE_AUTHENTICATED_PRINCIPAL` i `TEAMS_URL` mają domyślne wartości „lokalne". `docker run` bez zmiennych daje więc narzędzia bez tożsamości nasłuchujące na wszystkich interfejsach. W Azure oba ustawienia są podane jawnie (sprawdzone), więc dotyczy to wyłącznie ręcznego uruchomienia obrazu. Skutek jest ograniczony: `teams` w pętli zwrotnej **wewnątrz kontenera** nie odpowiada, więc takie wywołanie kończy się niedostępnością, a nie zapisem. | **OPEN** — uczciwa naprawa to `ENV REQUIRE_AUTHENTICATED_PRINCIPAL=true` w `Dockerfile` (Azure i tak ustawia `true`, `dev.ps1` nie używa obrazu). Poza zadaniami tej zmiany, zapisane zamiast dołożone po cichu |
| — | `config.py:29` | Sprawdzone celowo, nie znalezisko: adres, którego `urlparse` nie umie rozłożyć na host, wypada jako **nie**-pętla zwrotna, więc własność jest wtedy fałszywa. Domyślnie zamknięte, nie otwarte. | verified |

Nie znaleziono ścieżki obejścia seamu: `operator_token` jest importowane wyłącznie w
`tools/_shared.py`, a wszystkie dwanaście narzędzi woła `teams` przez `_call` — sprawdzone
grepem po `teams_mcp/`, nie założone z lektury jednego pliku.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **Brak tożsamości operatora zatrzymuje zapis, nie podstawia zastępczej** | — |
| Żądanie zapisujące bez tożsamości za warstwą uwierzytelniającą | `tests/test_local_operator.py::test_a_write_is_refused_there_too_and_never_reaches_teams`, `tests/test_operator.py::test_a_call_with_no_operator_header_is_refused_naming_the_absence` |
| Odczyt bez tożsamości za warstwą uwierzytelniającą | `tests/test_local_operator.py::test_the_same_call_is_refused_where_an_identity_could_have_existed` |
| Zdalny `teams` bez warstwy uwierzytelniającej przed modułem | `tests/test_local_operator.py::test_a_remote_teams_refuses_even_with_no_authenticator_in_front` (w tym asercja, że powód nie nazywa adresu), `tests/test_config.py::test_a_remote_teams_makes_an_operator_required_even_with_no_authenticator` |
| Maszyna deweloperska, gdzie nikt nie może być uwierzytelniony — wywołanie bez tożsamości | `tests/test_local_operator.py::test_a_read_with_nobody_behind_it_reaches_teams_carrying_no_identity`, `::test_a_write_with_nobody_behind_it_reaches_teams_the_same_way`, `tests/test_client.py::test_no_token_means_no_authorization_header_at_all`, `::test_a_write_with_no_token_carries_no_authorization_either` |
| …to samo, w części „MUST być widoczne w terminalu na tej samej liście" | **brak testu** — patrz Gaps |
| Moduł mówi, w którym stanie wstał | `tests/test_local_operator.py::test_the_module_says_at_startup_that_tools_act_without_an_identity`, `::test_the_module_says_the_other_state_when_an_operator_is_required` |
| Tożsamość z argumentu narzędzia pozostaje bez znaczenia w każdym stanie | `tests/test_local_operator.py::test_no_tool_takes_an_identity_as_an_argument_in_any_shape` (schematy publikowane przez `list_tools`, nie źródło), `tests/test_operator.py::test_the_modules_own_authorization_header_is_not_mistaken_for_the_operators` |
| Warunek jako taki — oba składniki osobno i razem | `tests/test_config.py::test_an_absent_operator_is_tolerated_only_in_the_full_local_shape`, `::test_an_authenticator_in_front_makes_an_operator_required_even_on_loopback`, `::test_a_remote_teams_makes_an_operator_required_even_with_no_authenticator`, `::test_the_deployed_shape_requires_an_operator_on_both_counts`, `::test_localhost_and_ipv6_loopback_count_as_this_machine` |
| Domyślność ostrożnej gałęzi | `tests/test_operator.py::test_requiring_an_operator_is_what_happens_by_default`, `::test_a_present_token_is_still_carried_when_an_absent_one_would_be_tolerated` |

Trzy scenariusze nie miały testu, dopóki ten przegląd ich nie policzył — zapis odmawiany za
uwierzytelniaczem, zdalny `teams` bez uwierzytelniacza i tożsamość w argumencie. Zostały
dopisane przed napisaniem tej tabeli, nie zgłoszone jako luki.

## Gaps

- **Widoczność w terminalu** (`teams-mcp-authorship`, scenariusz maszyny deweloperskiej,
  trzeci `AND`) jest twierdzeniem o dwóch modułach naraz: `teams` przypisuje `anonymous`
  nieuwierzytelnionemu żądaniu i terminal lokalnie dostaje to samo. Każda połowa jest
  przetestowana w swoim module; złączenie dowodzi tylko uruchomiony stos. Zadanie 5.2, do
  operatora.
- **Zadanie 4.5 wylądowało w innym pliku, niż mówiło.** Miało być w
  `tests/test_catalogue_tools.py`; ten plik ma `pytestmark = usefixtures("signed_in")` na
  poziomie modułu, więc każdy test w nim dostaje token — czyli dokładnie to, czego te testy
  mają nie mieć. Powstał `tests/test_local_operator.py`.
- **Znalezisko z `Dockerfile` zostaje otwarte** — wyżej, z zapisanym powodem.
