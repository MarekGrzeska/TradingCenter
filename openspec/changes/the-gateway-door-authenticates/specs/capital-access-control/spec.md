## ADDED Requirements

### Requirement: Tożsamość pochodzi wyłącznie ze zwalidowanego tokenu

Moduł rozpoznaje uwierzytelnionego wołającego z oświadczeń tokenu. Oświadczenia MUST pochodzić z
tokenu, który ktoś zweryfikował — podpis, wystawca i audiencja — zanim moduł uzna kogokolwiek za
rozpoznanego. Nagłówek niosący oświadczenia, którego nie poprzedziła weryfikacja, MUST NOT być
traktowany jako tożsamość: jest wtedy tym samym, czym jest nagłówek od dowolnego wołającego, czyli
danymi, a nie stwierdzeniem.

Wdrożenie MUST postawić przed modułem uwierzytelniającego, który **odrzuca** token nieważny,
zamiast przepuszczać żądanie dalej bez oświadczeń. Konfiguracja, w której nieważny token dociera
do modułu nierozpoznany, MUST być traktowana jako niespełnienie tego wymagania, a nie jako
łagodniejszy wariant — jej objawem jest odmowa dla każdego wołającego z przeglądarki, nieodróżnialna
od wygasłej sesji operatora.

Wymaganie MUST dać się sprawdzić z zewnątrz, bez wiedzy o konfiguracji: żądanie z tokenem
nieważnym MUST zostać odrzucone, zanim dotknie modułu.

#### Scenario: Nieważny token nie dociera do modułu

- **WHEN** przychodzi żądanie z tokenem, którego nie da się zweryfikować
- **THEN** zostaje odrzucone, zanim dotknie modułu
- **AND** odmowa pochodzi od warstwy uwierzytelniającej, nie od rejestru tras modułu

#### Scenario: Oświadczenia bez weryfikacji nie są tożsamością

- **WHEN** żądanie niesie nagłówek z oświadczeniami, którego nie poprzedziła weryfikacja tokenu
- **THEN** moduł MUST NOT uznać wołającego za rozpoznanego
- **AND** odpowiada tak, jak na wywołanie bez poświadczenia

#### Scenario: Terminal z ważnym tokenem zostaje rozpoznany

- **WHEN** terminal wywołuje trasę rachunku z ważnym tokenem swojej aplikacji
- **THEN** żądanie dociera do modułu z oświadczeniami, którym moduł może wierzyć
- **AND** dalszy dostęp rozstrzyga rejestr tras
