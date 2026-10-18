## REMOVED Requirements

### Requirement: Bot z przypisaniem nie znika po cichu
**Reason**: Brama nie ma już przypisań. Reguły wskazujące adresata leżą w pakiecie alertów, którego brama nie może czytać.
**Migration**: Reguła wskazująca adresata usuniętego bota zostaje zapisana i jest oznaczona w zakładce Alerty, a jej odpalenia są zapisywane jako nieudane z powodem „adresat nie istnieje” (`alerts-rules`). Ostrzeżenie przenosi się do potwierdzenia usunięcia w zakładce Telegram (`terminal-telegram`).
