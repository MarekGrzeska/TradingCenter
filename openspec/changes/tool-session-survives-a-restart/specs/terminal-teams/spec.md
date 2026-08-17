## Purpose

Zakładka, w której operator składa zespół i patrzy, jak pracuje: co widać na obrazie zespołu,
jak edytuje się role i zależności, skąd bierze się lista katalogu i co pokazuje przebieg
w trakcie.

## ADDED Requirements

### Requirement: Zakończony przebieg pokazuje treść każdego wywołania, także obserwowanego na żywo

Kiedy przebieg się kończy, terminal MUST doczytać nagrane wywołania narzędzi i pokazywać ich
argumenty oraz odpowiedzi — również tych wywołań, które przyszły strumieniem w trakcie
obserwowania i przyszły bez treści.

Bez tego operator, który patrzył na przebieg od początku, widzi mniej niż ten, który otworzył
go po fakcie — a to pierwszy z nich siedzi przy nieudanym zleceniu i pyta, co dokładnie
zostało wysłane. Odczyt po zakończeniu jest też momentem, w którym nagrane wiersze są
kompletne: przebieg nie dopisze już żadnego.

Lista wywołań po tym odczycie MUST NOT nieść tego samego wywołania dwa razy.

#### Scenario: Wywołanie obserwowane na żywo, czytane po zakończeniu

- **WHEN** przebieg kończy się, a operator rozwija wywołanie, które przyszło strumieniem
- **THEN** widzi jego argumenty i wynik albo powód odmowy
- **AND** wpis nie mówi już, że treść nie została odczytana

#### Scenario: Wywołanie nagrane i to samo wywołanie ze strumienia

- **WHEN** to samo wywołanie dotarło strumieniem i zostało doczytane z nagranych wierszy
- **THEN** okno pokazuje je jeden raz
