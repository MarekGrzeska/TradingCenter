## Purpose

Pozwala zauważyć, że pętla próbkowania w module `polymarket-data` przestała chodzić — awarię, której nie
widać z zewnątrz, bo proces stoi, trasa dostępności odpowiada, a archiwum po prostu przestaje
rosnąć.

## ADDED Requirements

### Requirement: Moduł publikuje wiek ostatniego ukończonego przebiegu pętli

Pętla pyta providera o każde śledzone zdarzenie i zapisuje próbkę. Moduł MUST publikować, jak dawno ta pętla ostatnio **ukończyła** przebieg, i MUST
mierzyć to w jej własnych interwałach, a nie w sekundach.

Jednostka jest wymaganiem, nie szczegółem. Próbkowanie co minutę i zbieranie co pięć są oba
zdrowe, a jeden próg wyrażony w sekundach byłby zły dla jednego z nich — ta sama decyzja,
którą `market-data-monitoring` podjęło dla wieku świecy.

#### Scenario: Pętla chodzi

- **WHEN** pętla kończy przebieg
- **THEN** publikowany wiek wraca do zera i rośnie od nowa

#### Scenario: Pętla stanęła

- **WHEN** od ostatniego ukończonego przebiegu minęło więcej niż kilka interwałów pętli
- **THEN** publikowana wartość rośnie dalej, aż operator ma o czym zostać powiadomiony

### Requirement: Przebieg, który się nie udał, nie liczy się jako przebieg

Moduł MUST NOT odnotowywać przebiegu, który zakończył się błędem. Pętla przeżywa własne
awarie celowo — jeden zły przebieg nie kończy zbierania — i właśnie dlatego odnotowanie go
zamieniłoby ten licznik w miarę tego, że pętla *się budzi*, a nie że *pracuje*.

#### Scenario: Przebieg kończy się błędem

- **WHEN** przebieg pętli kończy się wyjątkiem, a pętla idzie dalej
- **THEN** publikowany wiek nie wraca do zera

#### Scenario: Proces wstał i nie zdążył jeszcze nic ukończyć

- **WHEN** moduł działa, ale żaden przebieg jeszcze się nie zakończył
- **THEN** publikowana wartość MUST być na tyle duża, żeby czytało się to jako problem, a nie
  jako świeżo ukończony przebieg

### Requirement: Trasa dostępności zostaje niezmieniona

Moduł MUST NOT umieszczać wieku przebiegu w odpowiedzi trasy dostępności osiągalnej bez
uwierzytelnienia. Ta trasa mówi, że proces żyje — czy jego praca idzie dobrze, jest innym
pytaniem, a sonda czerwieniejąca od spóźnionej pętli nazywa martwym kontener, który żyje.

Wiek MAY być częścią odpowiedzi trasy stanu wymagającej uwierzytelnienia, gdzie czyta go
człowiek, a nie prober.

#### Scenario: Sonda pyta o dostępność, gdy pętla jest spóźniona

- **WHEN** pętla nie ukończyła przebiegu od wielu interwałów, a proces odpowiada
- **THEN** trasa dostępności nadal potwierdza, że proces żyje, i nie niesie wieku przebiegu
