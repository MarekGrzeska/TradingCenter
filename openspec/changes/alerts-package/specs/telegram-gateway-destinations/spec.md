## REMOVED Requirements

### Requirement: Adresat z przypisaniem nie znika po cichu
**Reason**: Brama nie ma już przypisań. Reguły wskazujące adresata leżą w pakiecie alertów, którego brama nie może czytać.
**Migration**: `alerts-rules`: reguła ze znikającym adresatem to stan reguły, widoczny na liście reguł. Ostrzeżenie przenosi się do potwierdzenia usunięcia w zakładce Telegram (`terminal-telegram`).
