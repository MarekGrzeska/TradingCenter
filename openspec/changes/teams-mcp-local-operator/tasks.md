## 1. Warunek w konfiguracji

- [x] 1.1 Wyprowadzić rozpoznawanie pętli zwrotnej z ciała `Settings._upstream_mode_is_coherent` do własnej funkcji i zawołać ją z walidatora
- [x] 1.2 Dodać w `Settings` własność mówiącą, czy brak tożsamości operatora jest dopuszczalny — oba warunki naraz
- [x] 1.3 Testy w `tests/test_config.py`: własność prawdziwa tylko przy wyłączonym `require_authenticated_principal` i pętli zwrotnej, fałszywa przy każdej z połówek osobno

## 2. Brak tożsamości jako świadomy stan

- [x] 2.1 `operator.py`: `operator_token` przyjmuje informację, czy brak tożsamości jest dopuszczalny, i zwraca `str | None`; komunikat odmowy zostaje słowo w słowo
- [x] 2.2 Docstring `operator.py` opisuje granicę wymagania, a nie samą odmowę
- [x] 2.3 `client.py`: `token: str | None` w `get`/`post`/`put`/`_request`/`_send`; przy `None` nagłówek `Authorization` **nie jest wysyłany**
- [x] 2.4 `TeamsClient` udostępnia warunek z zadania 1.2, żeby dojechał do warstwy narzędzi bez zmiany sygnatur `tools.register`
- [x] 2.5 `tools/_shared.py::_call` podaje warunek do `operator_token` i przekazuje `None` dalej bez własnej decyzji

## 3. Stan widoczny przy starcie

- [x] 3.1 Jedna linia logu przy starcie, gdy narzędzia działają bez tożsamości — nazywająca oba warunki, które do tego doprowadziły
- [x] 3.2 Test, że linia pada w trybie lokalnym i nie pada w żadnym innym

## 4. Testy zachowania

- [x] 4.1 `tests/test_operator.py`: odmowa za warstwą uwierzytelniającą i przy zdalnym `teams` (obie połówki osobno), z powodem nazywającym brak tożsamości
- [x] 4.2 `tests/test_operator.py`: brak tożsamości dopuszczony w pełnym kształcie lokalnym
- [x] 4.3 `tests/test_client.py`: wywołanie bez tokena nie niesie nagłówka `Authorization`, a z tokenem niesie `Bearer`
- [x] 4.4 `tests/conftest.py`: dubler pozwalający zbudować oba kształty, bez utrwalania dzisiejszej odmowy jako jedynej możliwej
- [x] 4.5 Test przez seam narzędzia (`test_catalogue_tools.py`): odczyt i zapis w trybie lokalnym dochodzą do `teams`, a poza nim odmawiają
- [x] 4.6 `uv run ruff check .`, `uv run pyright`, `uv run pytest` w `modules/teams-mcp`

## 5. Dokumentacja i domknięcie

- [x] 5.1 `modules/teams-mcp/README.md`: sekcja o tym, czyim imieniem moduł woła i co znaczy uruchomienie lokalne
- [ ] 5.2 Sprawdzić na uruchomionym stosie: `list_models` z czatu odpowiada, zespół założony z czatu jest w zakładce Teams tego samego terminala
- [x] 5.3 `review.md` po implementacji, przed archiwizacją
- [ ] 5.4 Zarchiwizować **po** `add-teams-mcp` — inaczej `MODIFIED` nie ma czego zmieniać (`design.md`, Migration Plan)
