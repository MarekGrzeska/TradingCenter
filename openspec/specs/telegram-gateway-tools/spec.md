# telegram-gateway-tools Specification

## Purpose
Zestaw narzędzi, który brama publikuje klientowi MCP: co model może przez nią zrobić — bo tu, w
odróżnieniu od archiwów, może zrobić coś widocznego poza tym systemem — i gdzie przebiega granica.
## Requirements
### Requirement: Model wysyła, ale nie zakłada i nie wiąże

Zestaw MUST zawierać narzędzie wysyłające wiadomość i narzędzie wyliczające adresatów. Zestaw MUST
NOT zawierać narzędzia zakładającego bota, kasującego bota ani wiążącego adresata.

Wysłanie jest jedynym aktem tej bramy, który da się odkręcić rozmową — powiedzeniem następnej
rzeczy. Założony bot i związany adresat zostają po rozmowie i należą do operatora.

#### Scenario: Powierzchnia narzędziowa

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** MUST znaleźć wysyłanie i odczyt adresatów, i MUST NOT znaleźć zakładania ani wiązania

### Requirement: Model widzi adresatów, zanim zaadresuje

Zestaw MUST pozwalać modelowi poznać nazwy adresatów bez wiedzy zdobytej gdzie indziej. Model MUST
NOT musieć znać nazwy adresata z góry, żeby cokolwiek wysłać.

#### Scenario: Pierwsze powiadomienie w rozmowie

- **WHEN** operator prosi model o wysłanie powiadomienia, nie podając adresata
- **THEN** model MUST móc odczytać listę adresatów i użyć jednego z nich

### Requirement: Brak adresatów jest odpowiedzią, nie awarią

Narzędzie wysyłające MUST odmówić w sposób, z którego model odczyta, że brama nie ma jeszcze
żadnego adresata i że związanie go jest robotą operatora poza rozmową.

Model, który dostaje w tej sytuacji błąd bez treści, powie operatorowi, że powiadomienie zostało
wysłane, albo że system jest zepsuty — obie odpowiedzi są nieprawdziwe.

#### Scenario: Brama pusta

- **WHEN** model woła narzędzie wysyłające, a brama nie zna żadnego adresata
- **THEN** odpowiedź narzędzia MUST nazwać ten stan i MUST wskazać, że wiąże go operator
