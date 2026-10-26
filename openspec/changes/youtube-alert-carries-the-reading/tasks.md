## 1. Pakiet alertów

- [x] 1.1 `template`: limit całej treści 16 000, `parts()` dzieli na części do 3500 (akapit → linia → słowo → twarde cięcie); `contract.EventIn.text` do 16 000
- [x] 1.2 Migracja `0004`: `fires.parts_sent int NOT NULL DEFAULT 0`; `store.claim_deliveries` zwraca ją, `store.part_sent` ją podbija
- [x] 1.3 `delivery`: wysyła części od `parts_sent`, po każdej zapisuje postęp; odpalenie z doręczoną częścią omija sufit
- [x] 1.4 Testy: podział, trzy części doręczone w kolejności, ponowienie od niedoręczonej

## 2. Archiwum YouTube

- [x] 2.1 `store.analysed_for_alert` czyta tekst odczytu; `alerts.message` niesie tekst odczytu, cięty ze znakiem, odnośnik na końcu; opis typu zdarzenia
- [x] 2.2 Testy wiadomości; `youtube_data/README.md`
- [x] 2.3 `contract-sync`; `ruff` · `pyright` · `pytest` (z `-m db`)
