## ADDED Requirements

### Requirement: Edytor pokazuje szkic agenta

Po każdej zakończonej turze zakładka MUST przeczytać szkic otwartej strategii (albo nowej, gdy strategia nie jest jeszcze
zapisana) i, gdy jest nowszy od ostatnio pokazanego, MUST wstawić go do edytora jako niezapisany tekst, z walidacją i
streszczeniem jak przy pisaniu ręcznym, i MUST powiedzieć, że wpisał go agent. Otwarcie strategii ze szkicem nowszym od
jej ostatniej rewizji MUST pokazać szkic. „Porzuć zmiany” MUST usuwać szkic, a „Nowa…” MUST usuwać szkic nowej strategii.

#### Scenario: Agent zmienia stop przed zapisem

- **WHEN** operator prosi w czacie strategii „zmień stop na 1,5 ATR”, a agent kładzie szkic
- **THEN** po turze edytor MUST pokazywać szkic jako niezapisane zmiany, a streszczenie MUST dotyczyć szkicu

#### Scenario: Porzucenie szkicu

- **WHEN** operator klika „Porzuć zmiany” przy szkicu agenta
- **THEN** edytor MUST wrócić do zapisanej rewizji, a szkic MUST zostać usunięty
