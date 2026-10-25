## 1. Pakiet strategii

- [x] 1.1 Migracja `0004`: `strategy_drafts` (miejsce: strategia albo nowa, dokument, chwila, numer kolejny)
- [x] 1.2 `drafts.py`: zapis, odczyt, usunięcie; usunięcie przy zapisie rewizji i utworzeniu strategii
- [x] 1.3 Trasy `GET`/`DELETE` `/strategies/{id}/draft` i `/drafts/new`, rekord wołających, kontrakt
- [x] 1.4 Narzędzie `draft_strategy`, opisy i `HOW_TO_WRITE` (szkic, polskie opisy), sufit powierzchni
- [x] 1.5 Testy: szkic nie tworzy rewizji, zapis rewizji usuwa szkic, trasy
- [x] 1.6 Streszczenie oddaje zmienną jej formułą; test

## 2. Agent

- [x] 2.1 Kontekst strategii: zmiany szkicem, rewizja na prośbę

## 3. Terminal

- [x] 3.1 Skill `contract-sync`
- [x] 3.2 Szkic po turze i przy otwarciu, „Porzuć zmiany” i „Nowa…” usuwają szkic
- [x] 3.3 Testy: szkic po turze trafia do edytora jako niezapisany

## 4. Zamknięcie

- [ ] 4.1 README pakietu, `review.md`
