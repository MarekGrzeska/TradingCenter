## 1. Moduł

- [x] 1.1 Wycofanie wyłącza harmonogramy i wyzwalacze zespołu w jednej transakcji
- [x] 1.2 `claim_due` i `select_due` pomijają wiersze wycofanych zespołów
- [x] 1.3 `GET /teams?archived=true` z `archived_at`; `POST /teams/{id}/restore`
- [x] 1.4 Testy: store (wycofanie, przywrócenie, zegar) i trasa

## 2. Terminal

- [x] 2.1 Regeneracja kontraktu, `listRetiredTeams` i `restoreTeam` w `teamsApi`
- [x] 2.2 Przełącznik Active / Retired i lista wycofanych z przywróceniem
- [x] 2.3 Testy widoku: lista, przywrócenie, błąd
