## REMOVED Requirements

### Requirement: Zestaw narzędzi wyłącznie czyta

**Reason**: Moduł `market-mcp` przestaje istnieć; zestaw narzędzi publikuje odtąd archiwum.
**Migration**: `market-data-tools`, wymaganie o tej samej nazwie — treść bez zmian, z jednym
dopisanym akapitem i scenariuszem: zakaz zapisu MUST być odtąd sprawdzany testem, bo
narzędzia stoją w tym samym procesie co zapis, więc nie chroni ich już klient HTTP
odmawiający każdej metody zapisującej.

### Requirement: Zestaw odpowiada na pytania o archiwum

**Reason**: Jak wyżej — wymaganie przenosi się razem z zestawem narzędzi.
**Migration**: `market-data-tools`, wymaganie o tej samej nazwie, treść bez zmian.

### Requirement: Zestaw odpowiada na pytania o wskaźniki

**Reason**: Jak wyżej.
**Migration**: `market-data-tools`, wymaganie o tej samej nazwie, treść bez zmian.

### Requirement: Opis narzędzia jest częścią kontraktu

**Reason**: Jak wyżej.
**Migration**: `market-data-tools`, wymaganie o tej samej nazwie, treść bez zmian.

### Requirement: Powierzchnia narzędzi ma zapisany sufit

**Reason**: Jak wyżej. Sufit 19 700 znaków obowiązuje dalej — koszt powierzchni płaci model
w każdej turze i nie zmienia go to, że dane są bliżej.
**Migration**: `market-data-tools`, wymaganie o tej samej nazwie, z dopisanym akapitem
o schemacie odpowiedzi. Schemat wyjścia MUST zostać: to jedyny mechanizm, który w tym
repozytorium wykrył realną awarię odpowiedzi narzędzia, a przeniesienie kodu jest dokładnie
tą chwilą, w której mógłby po cichu zniknąć.
