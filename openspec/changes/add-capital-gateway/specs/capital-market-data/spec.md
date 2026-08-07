## Purpose

Serves what an instrument is and what it did: finding tradeable symbols, and reading their
candle history — including history deeper than one provider request can return.

## ADDED Requirements

### Requirement: Instruments are searchable and enumerable

The module SHALL let a consumer find instruments by phrase and enumerate the whole catalogue.
Every instrument SHALL carry a symbol, a name, an asset class and whether it is tradeable.

#### Scenario: Searching by phrase

- **WHEN** a consumer searches for a phrase
- **THEN** the module returns matching instruments with symbol, name, asset class, tradeable
  flag, and current bid and ask where the provider supplies them

#### Scenario: Enumerating the catalogue

- **WHEN** a consumer enumerates instruments
- **THEN** the result contains no duplicate symbols
- **AND** it states whether the traversal was cut short by its own bound, so a partial
  catalogue is never mistaken for a complete one

#### Scenario: A branch of the catalogue is unreadable

- **WHEN** part of the catalogue cannot be read
- **THEN** that part is skipped and the rest is returned, rather than failing the whole read

### Requirement: Candles are read at a stated resolution

The module SHALL serve candles for a symbol at a stated resolution, oldest first, with no
duplicate timestamps. Supported resolutions SHALL be `MINUTE`, `MINUTE_5`, `MINUTE_15`,
`MINUTE_30`, `HOUR`, `HOUR_4`, `DAY` and `WEEK`.

#### Scenario: Reading recent candles

- **WHEN** a consumer asks for candles of a symbol at a resolution
- **THEN** the response is ordered oldest first, contains no repeated timestamp, and states the
  resolution on every candle

#### Scenario: An unknown symbol

- **WHEN** a consumer asks for candles of a symbol the provider does not know
- **THEN** the module answers with a not-found error naming the symbol

### Requirement: One price side is used everywhere

Candles SHALL be built from the bid side of the provider's quotes, for both history and live
data, so that a series assembled from both is continuous.

#### Scenario: History meets live data

- **WHEN** a consumer joins historical candles to candles received live for the same symbol
- **THEN** the two carry the same price convention and the join introduces no step

### Requirement: History is paged beyond the provider's ceiling

The provider returns at most 1000 candles per request and refuses a date window wider than the
requested count. The module SHALL page backwards to satisfy a larger request, and each further
window SHALL be anchored on the oldest candle already collected rather than on the clock — a
market that was shut returns fewer candles than the calendar implies.

#### Scenario: Asking for more candles than one request allows

- **WHEN** a consumer asks for more candles than the provider serves in one request
- **THEN** the module issues as many requests as needed and returns a single series, ordered
  oldest first and free of duplicate timestamps

#### Scenario: The instrument's history runs out

- **WHEN** paging reaches the point where the provider has no older data
- **THEN** the module stops and returns what it collected, which is not an error
- **AND** the response states that the series is shorter than requested because history ended

#### Scenario: A window returns nothing new

- **WHEN** a further window yields no candle older than the oldest already held
- **THEN** paging stops rather than repeating the same window

### Requirement: A deep read reports its progress and its cost

A deep history read may take tens of seconds and dozens of provider requests. The module SHALL
report, with the result, how many candles were collected, how many requests it took, and the
period the series covers.

#### Scenario: Completing a deep read

- **WHEN** a deep history read completes
- **THEN** the response states the candle count, the number of provider requests issued, and the
  first and last timestamps covered

#### Scenario: The caller abandons a deep read

- **WHEN** the consumer disconnects while a deep read is in flight
- **THEN** the module stops issuing further provider requests
