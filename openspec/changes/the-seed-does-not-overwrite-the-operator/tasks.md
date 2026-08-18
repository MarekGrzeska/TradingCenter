## 1. Baza odróżnia zasiew od zapisu operatora

- [x] 1.1 migracja `0013`: kolumna `source` (`seed` | `operator`) z CHECK-iem
- [x] 1.2 backfill wg reguły z `design.md` D2 — wersje `v4`–`v11` wpisane literałem
- [x] 1.3 deduplikacja: przy kolizji wcześniejszy wiersz operatora dostaje wolną wersję (D3)
- [x] 1.4 unikat na `version`, **po** 1.3, w tej samej migracji

## 2. Zasiew ustępuje operatorowi

- [x] 2.1 helper zasiewu — `INSERT ... SELECT ... WHERE` najnowszy wiersz jest zasiewem
- [x] 2.2 `create_prompt_revision` zapisuje `source = 'operator'`
- [x] 2.3 `PromptRevision` niesie `source` (model magazynu, nie drut — design.md, Open Questions)

## 3. Testy

- [x] 3.1 zasiew po zapisie operatora nie wchodzi; zasiew po zasiewie wchodzi (D3, zasada nr 5)
- [x] 3.2 dwa zapisy o tej samej wersji odrzucone przez bazę
- [x] 3.3 backfill: reguła D2 na wierszach udających historię, z kolizją włącznie
- [x] 3.4 regresja: wersja operatora i wersja następnego zasiewu przestają być tą samą

## 4. Domknięcie

- [x] 4.1 `uv run pytest`, `ruff`, `pyright` w agent
- [x] 4.2 `openspec validate --strict`
