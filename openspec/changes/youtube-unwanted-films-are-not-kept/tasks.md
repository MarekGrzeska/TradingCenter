## 1. Nie przechowywać

- [x] 1.1 `store.upsert_films` z progami nie zapisuje filmu spoza nich; `drop_unwanted` kasuje film, który okazał się spoza progów, i stare wiersze „pominięty”
- [x] 1.2 Pętla i wskazanie ręczne przekazują progi; ręczne wskazanie spoza progów jest odrzucone z powodem
- [x] 1.3 Testy: film spoza progów nie wraca przy ponownym listowaniu, premiera kasowana po otrzymaniu długości, ręczny short odrzucony; README i objaśnienie
