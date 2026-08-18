## Why

Na maszynie deweloperskiej **każde** narzędzie `teams-mcp` odmawia — także czytające. Nikt
lokalnie nie uwierzytelnia terminala, więc `agent` nie ma czego przenieść dalej
(`agent/routers/sessions.py`: „Absent — local development, where nothing authenticates —
those tools refuse and say why"), a `teams_mcp/operator.py` odmawia przy braku tokena.
Skutkiem jest moduł, którego całej powierzchni — zakładania zespołów, poprawiania rewizji,
uruchamiania przebiegów, harmonogramów — nie da się ruszyć poza Azure ani jednym wywołaniem.
Pierwszy odczyt z czatu na uruchomionym stosie kończy się dziś na `list_models · refused`.

Odmowa jest słuszna za Easy Authem i nie jest do zniesienia. Brakuje jej wyłącznie granicy:
dzisiaj obowiązuje też tam, gdzie nie ma żadnej warstwy uwierzytelniającej, która mogłaby
jakikolwiek token wystawić.

## What Changes

- **`teams-mcp` przyjmuje brak tokena operatora wyłącznie w pełnym kształcie lokalnym**:
  gdy przed modułem nie stoi uwierzytelniacz (`REQUIRE_AUTHENTICATED_PRINCIPAL=false`)
  **i** `TEAMS_URL` wskazuje pętlę zwrotną. Dwa warunki, bo każdy z nich osobno jest
  możliwą pomyłką w konfiguracji, a razem opisują maszynę, na której nikt nie może być
  uwierzytelniony.
- **W tym trybie moduł woła `teams` bez nagłówka `Authorization`**, a `teams` przypisuje
  własny principal `anonymous` (`teams/auth.py`, `UNAUTHENTICATED`) — dokładnie ten sam,
  jaki lokalnie dostaje terminal. Zespół założony z czatu trafia więc na tę samą listę, co
  złożony ręcznie, i daje się otworzyć.
- **W Azure nie zmienia się nic.** `REQUIRE_AUTHENTICATED_PRINCIPAL=true` i zdalne
  `TEAMS_URL` (`infra/app-service.tf`) wykluczają ten tryb po obu warunkach naraz, więc
  brak tokena zostaje odmową — dla zapisów i odczytów tak samo jak dziś.
- **Zasada „tożsamość jest przenoszona, a nie odgadywana" zostaje nietknięta.** Tryb lokalny
  nie zgaduje operatora ani nie czyta go z argumentu narzędzia — nie przenosi żadnej
  tożsamości i pozwala `teams` przypisać tę, którą i tak przypisuje lokalnie każdemu.
- **Moduł mówi to raz przy starcie**, zamiast pozwalać wnioskować z odmów, których nie ma.
- Testy utrwalające dzisiejszą odmowę (`tests/test_operator.py`, `tests/conftest.py`) są
  częścią tej zmiany, a nie jej ofiarą: odmowa zostaje, dochodzi jej warunek.

## Capabilities

### New Capabilities

Żadnych.

### Modified Capabilities

- `teams-mcp-authorship`: wymaganie „Brak tożsamości operatora zatrzymuje zapis, nie
  podstawia zastępczej" dostaje granicę — obowiązuje tam, gdzie tożsamość **mogła** być
  ustalona, czyli za warstwą uwierzytelniającą albo przy zdalnym `teams`. Dochodzi jawny
  scenariusz lokalny i jawne stwierdzenie, że `anonymous` nie jest tożsamością zastępczą
  wybraną przez ten moduł, lecz tą, którą `teams` przypisuje samo.

**Kolejność wobec `add-teams-mcp` i to jest twarde ograniczenie:** ta zdolność nie jest
jeszcze w `openspec/specs/` — mieszka w niezarchiwizowanej zmianie `add-teams-mcp`. Ta
zmiana MUST być archiwizowana **po** tamtej, bo inaczej `MODIFIED` nie ma czego zmieniać.

## Impact

- `modules/teams-mcp`: `operator.py` (warunek i jego komunikat), `client.py` (token
  opcjonalny — brak nagłówka, nie puste `Bearer`), `tools/_shared.py` (seam przekazujący
  brak dalej), `server.py` albo `__main__.py` (jedna linia logu przy starcie),
  `tests/test_operator.py`, `tests/conftest.py`, `tests/test_client.py`, `README.md`.
- **Bez zmian**: `teams`, `agent`, `terminal`, `infra/**` — produkcyjne ustawienia już mają
  oba warunki po stronie odmowy, więc `terraform apply` nie jest częścią tej zmiany.
- Bez zmian w kontraktach między modułami: nagłówek `x-operator-authorization` i wszystkie
  trasy `teams` zostają, jakie są.

## Zamknięcie

Zarchiwizowana 18 sierpnia 2026 z dwoma niezaznaczonymi polami, świadomie:

- **5.2** to sprawdzenie na uruchomionym stosie, wykonywane ręcznie. Zastąpione ruchem
  produkcyjnym: `add-teams-mcp` wdrożył moduł 17 sierpnia i od tego czasu agent zakłada
  zespoły z czatu. Weryfikacja odbyła się, tylko nie w rytmie tej listy.
- **5.4** żądało archiwizacji *po* `add-teams-mcp`. Ten warunek jest spełniony —
  `add-teams-mcp` jest w archiwum pod datą 17 sierpnia.

Bez `review.md`, co od 18 sierpnia 2026 jest dozwolonym stanem: artefakt jest opcjonalny
i pisany, gdy ma co powiedzieć (`openspec/config.yaml`, `rules.review`).
