## Verdict

Zakładka stoi na produkcji i operator jej używa. Grupy 1–8 weszły w całości, z grupy 9
zrobione są `apply`, wdrożenie i sprawdzenie 9.3; **9.6 — zdjęcie ustępstwa w gatewayu —
zostaje świadomie niezrobione**, bo dopóki gateway przyjmuje też publiczność `market-data`,
stary token jest siatką pod stopami. To jest odroczenie z powodem, nie zapomniana pozycja.

Rozdział publiczności tokenu okazał się większy niż zakładka, po którą go zrobiono: terminal
brał **jeden** token z publicznością `market-data` i wysyłał go do workbencha i gatewaya, a
gateway został skonfigurowany, żeby ją przyjmować. Pre-autoryzacje do proszenia po imieniu
stały nieużywane od sierpnia. Ta zmiana je wydała.

**Trzy rzeczy zepsuły się po drodze i dwie z nich na produkcji.** Preflight CORS odbijany 401
sprawiał, że działający moduł czytał się jako nieosiągalny; kontener listy bez `flex-1`
kończył zakładkę martwą przestrzenią i ucinał ostatnią kartę. Obie naprawione i sprawdzone
pomiarem przed i po.

## Verified

Uruchomione, nie zadeklarowane:

```
terminal   tsc -b --noEmit        (czysto)
           vite build             (czysto)
           eslint .               (czysto)
           vitest run             769 passed
           contract:check         Every contract is up to date
infra      terraform plan         2 to add, 2 to change, 0 to destroy
           terraform apply        Apply complete
           terraform plan (po)    No changes
```

Przeciw produkcji:

```
allowedApplications (polymarket-data)   [workbench, terminal]
TOOL_CALLER_APPLICATION_IDS             workbench
REST_CALLER_APPLICATION_IDS             terminal
zakres access_as_user                   istnieje, terminal pre-autoryzowany
bundle terminala                        cztery zakresy, zakładka obecna
OPTIONS /events  (przed CORS)           401
OPTIONS /events  (po)                   200 + Access-Control-Allow-Origin
GET /events bez tokenu                  401
```

**9.3 przechodzi** — Accounts, Teams i Graph działają po rozdziale publiczności, bez
dodatkowej zgody przy logowaniu. To było jedyne sprawdzenie, które mogło coś złapać, bo te
zakładki po raz pierwszy wożą własne publiczności.

Kolejność `apply` → wdrożenie zachowana i to nie było kosmetyczne: obraz terminala pyta
o zakres, którego bez applya nikt by nie pre-autoryzował.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| krytyczne | `infra/app-service.tf` | Brak bloku `cors` na polymarket-data. Preflight `OPTIONS` nie niesie tokenu, Easy Auth odbijał go 401, a odmowa na poziomie sieci dociera do `fetch` jako wyjątek — więc zakładka raportowała awarię modułu, który działał. Czwarty raz w tym repozytorium i pierwszy, w którym komentarz stojący w tym samym bloku już to zapowiadał. | FIXED `ea23e3c` |
| poważne | `PolymarketView.tsx` | Kontener przewijania bez `flex-1` — nigdy nie rósł, więc zakładka kończyła się martwą przestrzenią, a lista wyższa niż miejsce była ucinana zamiast przewijana. Dwa objawy, jedna przyczyna: rozwinięta karta urwana na nagłówku rynku wyglądała jak osobny błąd. | FIXED `a548d45` |
| poważne | `auth/entra.ts` | Po rozdzieleniu publiczności `acquire` dalej zerowało wspólne konto przy `InteractionRequiredAuthError` — brak zgody na zakres jednego modułu wylogowywał operatora z całego terminala. | FIXED |
| średnie | `EventCard.tsx` | Asynchroniczny `onChange` przy wyborze grupy bez obsługi błędu: odrzucone przypisanie było nieobsłużonym odrzuceniem, a kontrolka pokazywała dalej grupę, której nikt nie zapisał. | FIXED |
| drobne | `polymarketApi.ts` | `include_ended` wysyłane tylko gdy prawdziwe, przy serwerowym domyślnym `true` — czyli jedynej wartości wartej wysłania nie dało się wysłać. | FIXED |

Dwa błędy tej zmiany są tym samym błędem w dwóch warstwach: **kopia wzorca bez jednej
części.** `cors` — trzy inne aplikacje mają ten blok, ta go nie dostała. `min-h-0 flex-1
overflow-auto` — dwie inne zakładki mają tę trójkę, ta miała dwa z trzech. W obu przypadkach
komentarz albo sąsiad mówił, jak ma być.
