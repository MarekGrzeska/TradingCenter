## 1. Zakres na moduł

- [x] 1.1 `EntraConfig` niesie zakres na endpoint zamiast jednego; `acquire()` przyjmuje zakres wołanego modułu
- [x] 1.2 Każdy klient dostaje `Identity` swojego modułu — `jsonClient` bez zmiany podpisu, bo zakres siedzi w tożsamości, nie obok niej
- [x] 1.3 Brak zakresu dla modułu to `noIdentity`, nie cudzy token; praca lokalna (brak całej trójki) bez zmian
- [x] 1.4 `deploy-terminal.yml`: cztery zakresy jako literały obok adresów; `vars` zostają tylko dla client id i tenant id
- [x] 1.5 Testy: każdy klient wysyła zakres swojego modułu; token wzięty dla jednego nie trafia do drugiego; brak zakresu dla modułu to praca bez tożsamości, nie cudze poświadczenie
- [x] 1.6 `pnpm test`, `lint`, `typecheck`

## 2. Klient kontraktu

- [x] 2.1 `src/polymarket/` — klient po `contract.polymarket.generated.ts`, na `jsonClient` z zakresem tego modułu
- [x] 2.2 Mapowanie wire → domena dla obserwacji, migawki, historii i zmian; `Decimal` nie istnieje na wire, prawdopodobieństwo jest liczbą 0..1
- [x] 2.3 Odmowa z powodu tożsamości odróżniona od braku odpowiedzi na poziomie klienta
- [x] 2.4 Testy mapperów wire↔domena i obu kształtów porażki
- [x] 2.5 `pnpm test`, `lint`, `typecheck`, `contract:check`

## 3. Zakładka i lista

- [x] 3.1 Wpis w `src/app/tabs.ts` i widok; pusta lista nazwana jako pusta, ze wskazaniem, czym się ją zapełnia
- [x] 3.2 Wydarzenie → rynki → wyniki; rynek wielowynikowy jest kształtem, dwuwynikowy szczególnym przypadkiem
- [x] 3.3 Prawdopodobieństwa całej listy jednym żądaniem migawki; skala 0..1 nazwana w widoku
- [x] 3.4 Moment przy każdej cenie; cena starsza niż takt próbkowania odróżniona od bieżącej
- [x] 3.5 Zmiany w oknach 5m/15m/1h/4h/12h/24h/7d z momentem punktu bazowego; okno bez pokrycia jako brak z przyczyną, nie zero i nie puste pole. Pobierane przy otwarciu wydarzenia, nie dla całej listy — to żądanie na wydarzenie
- [x] 3.6 Odmowa wobec niedostępności modułu — dwa różne komunikaty
- [x] 3.7 Testy: rynek wielowynikowy, jedno żądanie na listę, okno bez pokrycia, odmowa wobec awarii
- [x] 3.8 `pnpm test`, `lint`, `typecheck`

## 4. Obserwacje i grupy

- [x] 4.1 Objęcie obserwacją adresem albo identyfikatorem; obie drogi dają tę samą obserwację
- [x] 4.2 Wydarzenie już obserwowane rozpoznane jako takie, bez drugiej obserwacji
- [x] 4.3 Odmowa z powodu sufitu pokazana z przyczyną i z tym, co zrobić najpierw
- [x] 4.4 Zakończenie obserwacji z uprzedzeniem, że dane zostają
- [x] 4.5 Grupy: utworzenie, przypisanie, skasowanie, ograniczenie listy do grupy
- [x] 4.6 Testy: po trzy na trasę CRUD (ścieżka szczęśliwa, błąd, odmowa); skasowanie grupy nie kończy obserwacji
- [x] 4.7 `pnpm test`, `lint`, `typecheck`

## 5. Wykres serii prawdopodobieństwa

- [x] 5.1 Wykres liniowy na `lightweight-charts`, osobny od `chart/Chart.tsx`; oś wartości 0..1, opisana
- [x] 5.2 Wybór wyniku i zakresu czasu
- [x] 5.3 Granica najstarszego osiągalnego momentu narysowana, nie domyślna z urwania się przebiegu
- [x] 5.4 Dziura w pokryciu zostaje dziurą — żadnego odcinka przez przerwę
- [x] 5.5 Testy: zakres sięgający przed granicę, przerwa w środku zakresu, seria pusta
- [x] 5.6 `pnpm test`, `lint`, `typecheck`

## 6. Kasowanie zebranej historii

- [x] 6.1 Czynność w zakładce, po trasie REST modułu
- [x] 6.2 Potwierdzenie nazywające zakres usunięcia i jego nieodwracalność
- [x] 6.3 Odstąpienie nie kasuje niczego
- [x] 6.4 Testy: potwierdzenie, odstąpienie, odmowa modułu
- [x] 6.5 `pnpm test`, `lint`, `typecheck`

## 7. Infrastruktura

- [x] 7.1 Delegowany zakres `access_as_user` na `module.polymarket_data_easy_auth`
- [x] 7.2 `azuread_application_pre_authorized` dla terminala przy tej rejestracji
- [x] 7.3 Terminal w `allowed_applications` modułu i w `REST_CALLER_APPLICATION_IDS`; `TOOL_CALLER_APPLICATION_IDS` bez zmian
- [x] 7.4 Output z zakresem terminala dla tego modułu, na wzór trzech istniejących
- [x] 7.5 `terraform fmt`, `validate`, plan lokalnie — **2 do dodania, 2 zmiany, 0 skasowań**. `apply` operatora, jeszcze niewykonany

## 8. Prawda w plikach

- [x] 8.1 README terminala: czwarty backend, czwarty zakres, i że token jest jeden na moduł
- [x] 8.2 `docs/architecture.md`: terminal czyta rynki predykcyjne; rozdział publiczności tokenu przestaje być planem
- [x] 8.3 `.env.example` terminala i komentarz przy `resolveEntra`

## 9. Wdrożenie i sprawdzenie

- [ ] 9.1 `apply` operatora — zakres, pre-autoryzacja i listy wołających **przed** wdrożeniem terminala
- [ ] 9.2 Wdrożenie terminala; logowanie przechodzi bez dodatkowej zgody
- [ ] 9.3 Sprawdzenie, że zakładki kont, zespołów i wykresu działają dalej po rozdziale zakresów
- [ ] 9.4 Sprawdzenie zakładki: lista, zmiany w oknach, przebieg z granicą pokrycia
- [ ] 9.5 Sprawdzenie odmów: wołający bez uprawnienia do REST odróżniony od modułu nieosiągalnego
- [ ] 9.6 Zdjęcie ustępstwa w gatewayu — osobny `apply`, po 9.3
- [ ] 9.7 `review.md` — co zmierzono, co odpowiedziało po wdrożeniu, i test na każdy scenariusz albo nazwana luka
