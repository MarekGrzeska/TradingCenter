## Why

Archiwum YouTube i Gemini jako dostawca transkrypcji (`add-youtube-archive`,
`youtube-transcripts-through-gemini`) działają lokalnie i nie dotykają produkcji: bez
`YOUTUBE_DATABASE_URL` pakiet się nie montuje. Ta zmiana to włączenie go — baza, dwa klucze, ustawienia
workbencha — w kolejności, która nie zostawia ani jednej chwili z procesem, który nie wstaje.

Kolejność jest tu rozstrzygnięciem, bo trzy pułapki tego repozytorium dotyczą dokładnie tego ruchu:
ustawienie wskazujące na pusty sekret App Service zostawia jako dosłowny tekst (proces odmawia startu),
baza przekazana modułowi bez nadania własności kończy się odmową na pierwszym `CREATE TABLE` (a pakiet
ma jeden proces z resztą workbencha), a pule połączeń są jednym budżetem 30 z 50 — i zajęte w 29.

## What Changes

- **Terraform**: baza `youtube`; dwa sekrety w Key Vault (`youtube-data-api-key`, `gemini-api-key`);
  zmienna `youtube_enabled` (domyślnie `false`), za którą stoją ustawienia workbencha: baza i pula,
  `data_api`, łańcuch `direct,gemini`, analizator `openai` na kluczu rozmowy, własna lista wołających
  REST (tylko terminal — pakiet zapisuje listę obserwacji i wydaje jednostki dostawców).
- **Pula**: pula Telegrama spada z 4 do 3, żeby YouTube dostał 2 (razem 30 z 30). Telegram robi jedno
  wywołanie HTTP na wiadomość i trzyma bota, miejsce docelowe i kursor — nie czytamy z niego po wierszu.
  `test_pool_budget.py` liczy teraz także pakiet YouTube.
- **`scripts/enable_youtube_prod.py`**: część operatora, której Terraform nie umie — nadanie własności bazy
  roli workbencha (`grant-schema-ownership.sql`, przez tymczasową regułę zapory zamykaną w `finally`) i
  zapis dwóch kluczy do Key Vault z lokalnego `.env`, przez plik tymczasowy, nigdy przez argument ani
  ekran. Domyślnie próba na sucho; `--apply` wymaga `--gemini-key-is-paid`.
- **Kolejność włączenia**: `apply` z `youtube_enabled=false` → skrypt → `youtube_enabled=true` i `apply`.
  Wycofanie: `youtube_enabled=false`, jeden restart.

Poza zakresem: retencja surowych transkrypcji (ToS Data API — 30 dni), Gemini jako analizator odczytu,
alerty o filmach do innego adresata niż `ALERT_DESTINATION` procesu.

## Capabilities

### New Capabilities

- `youtube-data-enablement`: ustawienia za jedną zmienną, skrypt operatora, pule w budżecie.

### Modified Capabilities

Brak. Pominięte: `design.md` (decyzje są w tym dokumencie i w komentarzach `infra/variables.tf`) i
`review.md` (nie ma tu logiki poza skryptem, który ma testy na to, czego nie wolno: wypisać wartość,
położyć ją w argumencie, zostawić otwartą zaporę).

## Impact

- `infra/`: `database.tf`, `key-vault.tf`, `variables.tf`, `app-service.tf`, `terraform.tfvars.example`.
- `scripts/`: `enable_youtube_prod.py` i jego testy; `tests/test_pool_budget.py`.
- `modules/workbench/telegram_gateway/config.py`: domyślna pula 3 (test budżetu wymaga zgodności z Terraform).
- **Zależność**: wchodzi po `add-youtube-archive` i `youtube-transcripts-through-gemini` — obraz musi
  zawierać pakiet, zanim ustawienia go zamontują (w odwrotnej kolejności ustawienia są po prostu ignorowane).
- **Operator**: `terraform apply` jest jego (CI nie dostaje praw do `azuread_*`), podobnie klucz Gemini w
  planie płatnym — darmowy plan pozwala Google używać przesłanych treści.
