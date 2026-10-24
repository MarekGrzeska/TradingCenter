## 1. Backend

- [x] 1.1 Migracja `0008`: `topics.retry_at`; `models.Topic`, `store` (zapis odroczenia, zniesienie przy udanym wyszukiwaniu); test migracji
- [x] 1.2 `SourceRefused` w `providers/base.py`; `data_api._get` podnosi go dla odpowiedzi zapłaconej (odmowa, kod błędu, nie-JSON); testy `data_api`
- [x] 1.3 `ingest._discover`: odroczenie po `SourceRefused` i `QuotaExceeded`, ponowienie po braku odpowiedzi, warunek „należny” uwzględnia odroczenie; testy pętli
- [x] 1.4 `contract.TopicOut.retry_at`; test REST
- [x] 1.5 README: odroczenie oraz sprostowanie zapisu powtórzonych porażek i pominięć

## 2. Terminal

- [x] 2.1 Skill `contract-sync`
- [x] 2.2 `Topic.retryAt` i linijka w Tematach; test widoku

## 3. Zamknięcie

- [x] 3.1 Sprostowanie w `archive/2026-10-24-youtube-topic-run-history/review.md`
- [x] 3.2 `openspec validate --strict`, `pytest`, `ruff`, `pyright`, `vitest`, `eslint`, `tsc`, `contract:check`
- [x] 3.3 `review.md`
