## Why

Rozmowa widzi reguły (`alert_rules`) i ich historię (`alert_fires`), ale gdy operator mówi „podnieś próg tej reguły do
1,12”, agent może to tylko opisać słowami — bez sprawdzenia, czy reguła po zmianie by działała. Szkic zmiany
(`alerts-change-by-sentence`) już umie to policzyć i sprawdzić; brakuje drogi z rozmowy.

## What Changes

- **Narzędzie `propose_alert_change(rule_id, change)`** na powierzchni narzędziowej pakietu. Zwraca regułę tak, jak by
  wyglądała po zmianie, z powodami, dla których nie zadziała, i z informacją, że **nic nie zapisano**. Ta sama funkcja
  co `POST /drafts` (`alerts/proposing.py`): ta sama walidacja i ten sam dobowy sufit tokenów — rozmowa nie ma własnego.
- **Narzędzie nie jest oznaczone jako tylko do odczytu**: kosztuje tokeny, a narzędzie `readOnlyHint` z liczbą w
  odpowiedzi katalog reguł oferowałby jako wartość do obserwowania.
- Zatwierdza operator w terminalu (Edytuj… z tymi wartościami albo „Zmień zdaniem…”). Czat nie ma „Zapisz”, a w terminalu
  nie ma adresowania, więc bez linku — odpowiedź mówi, gdzie kliknąć. Zespoły widzą to samo narzędzie; ogranicza je sufit.

**Poza zakresem:** zapis z rozmowy (nadal `MUST NOT`), link do formularza, tworzenie nowej reguły z rozmowy.

## Capabilities

### Modified Capabilities
- `alerts-api`: powierzchnia narzędziowa zyskuje narzędzie proponujące zmianę, które niczego nie zapisuje. Wymaganie
  „Rozmowa widzi reguły i odpalenia, nie zmienia ich” mieszka jeszcze w niezarchiwizowanym `alerts-package`, więc tu jest
  tylko dopisywanie; po archiwizacji tamtej zmiany wymaganie dostanie jedno zdanie o wyjątku.
