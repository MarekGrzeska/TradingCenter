## Purpose

Która tożsamość dochodzi do której powierzchni tej bramy — i dlaczego moduł sprawdza to sam, zamiast
wierzyć, że coś przed nim jest włączone.

## ADDED Requirements

### Requirement: Moduł sprawdza wywołującego sam

Moduł MUST sam odrzucić wywołującego, którego nie zna, nawet jeśli stoi za bramą uwierzytelniającą.
Tożsamość MUST być czytana z roszczenia identyfikującego **aplikację**, nigdy z nagłówka nazywającego
zalogowanego człowieka.

Brama platformy autoryzuje aplikację, a nie trasę — więc bez własnego sprawdzenia każdy dopuszczony
wywołujący sięga po każdą trasę. Nagłówek z człowiekiem nie istnieje dla tokenu wydanego aplikacji,
co zostało zmierzone 19 sierpnia 2026 na innym module tej grupy.

#### Scenario: Wywołujący spoza listy

- **WHEN** żądanie niesie ważny token aplikacji, której moduł nie zna
- **THEN** moduł MUST odmówić, zanim wykona jakąkolwiek pracę

### Requirement: Powierzchnia narzędziowa i kontrakt REST mają rozłączne listy

Moduł MUST prowadzić osobną listę wywołujących dopuszczonych do powierzchni narzędziowej i osobną
dla kontraktu REST. Obecność na jednej MUST NOT dawać dostępu do drugiej.

Podział nie przebiega między czytaniem a pisaniem — obie powierzchnie wysyłają. Przebiega tam, gdzie
`telegram-gateway-api` postawiło granicę: zakładanie bota i wiązanie adresata są tylko w REST.

#### Scenario: Klient narzędziowy sięga po trasę REST

- **WHEN** wywołujący dopuszczony wyłącznie do powierzchni narzędziowej woła trasę zarządzającą
- **THEN** moduł MUST odmówić

### Requirement: Odmowa nie zależy od kolejności ładowania

Sprawdzenie wywołującego MUST odbywać się przed wybraniem trasy, tak żeby trasa dodana później była
objęta nim bez osobnego pamiętania o tym.

#### Scenario: Nowa trasa

- **WHEN** do modułu dokłada się trasę i nie robi się przy niej nic więcej
- **THEN** MUST ona odmawiać nieznanemu wywołującemu tak samo jak pozostałe
