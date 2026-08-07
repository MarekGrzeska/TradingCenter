## Purpose

Everything that changes money: opening and closing positions, resting orders, attached stops,
and turning the provider's asynchronous acknowledgement into a result a caller can act on.

## ADDED Requirements

### Requirement: Open positions are readable

The module SHALL publish the open positions of the active account, each carrying its
identifier, symbol, direction, size, opening level and profit or loss.

#### Scenario: Reading positions

- **WHEN** a consumer reads positions
- **THEN** each entry carries identifier, symbol, direction, size, open level and profit or loss

#### Scenario: No positions are open

- **WHEN** the active account holds no position
- **THEN** the module returns an empty list, not an error

### Requirement: Orders are placed by type

The module SHALL accept `MARKET`, `LIMIT` and `STOP` orders. `LIMIT` and `STOP` SHALL require a
target level; a request without one SHALL be rejected before it reaches the provider. An order
MAY carry an attached stop-loss and take-profit.

#### Scenario: A market order

- **WHEN** a consumer places a MARKET order for a tradeable symbol
- **THEN** the module returns a settled result reporting the order as filled, with its
  identifier and the level it filled at

#### Scenario: A resting order

- **WHEN** a consumer places a LIMIT or STOP order with a target level
- **THEN** the module returns a settled result reporting the order as working
- **AND** the order appears among the working orders

#### Scenario: A resting order without a level

- **WHEN** a consumer places a LIMIT or STOP order with no target level
- **THEN** the module rejects the request without contacting the provider and names the missing
  field

#### Scenario: The provider refuses the order

- **WHEN** the provider rejects the order
- **THEN** the module returns a result marked rejected, carrying the provider's stated reason

### Requirement: An asynchronous deal is settled before it is reported

The provider acknowledges an order with a reference and settles it separately. The module SHALL
resolve that reference into an outcome before answering, and SHALL NOT report an unresolved
reference as success.

#### Scenario: Settlement arrives

- **WHEN** the provider settles a deal shortly after acknowledging it
- **THEN** the module returns the settled outcome — filled, working, closed, cancelled or
  updated as the action requires

#### Scenario: Settlement does not arrive in time

- **WHEN** the deal is still unsettled after the module has waited its bounded number of attempts
- **THEN** the module returns a result marked pending, carrying the reference so the caller can
  resolve it later
- **AND** the result is not reported as filled

### Requirement: Positions are closed and amended

The module SHALL close an open position by identifier, and SHALL set or remove its stop-loss and
take-profit. Each stop SHALL be independently settable, removable, or left untouched — an
omitted field SHALL NOT clear an existing level.

#### Scenario: Closing a position

- **WHEN** a consumer closes a position by identifier
- **THEN** the module returns a settled result reporting the position as closed

#### Scenario: Setting one stop and leaving the other

- **WHEN** a consumer sets a stop-loss and omits the take-profit
- **THEN** the stop-loss is set and the existing take-profit is unchanged

#### Scenario: Removing a stop

- **WHEN** a consumer explicitly clears the take-profit
- **THEN** the take-profit is removed from the position

#### Scenario: An amendment naming no stop

- **WHEN** a consumer submits an amendment that names neither stop
- **THEN** the module rejects it rather than issuing an empty change

### Requirement: Working orders are listed and cancelled

The module SHALL publish the resting orders of the active account and cancel one by identifier.

#### Scenario: Listing working orders

- **WHEN** a consumer lists working orders
- **THEN** each carries identifier, symbol, direction, size, order type, target level and any
  expiry

#### Scenario: Cancelling a working order

- **WHEN** a consumer cancels a working order by identifier
- **THEN** the module returns a settled result reporting it as cancelled
- **AND** it no longer appears among the working orders

### Requirement: Trading acts on the demo account only

Order placement, position closure, amendment and cancellation SHALL be reachable only while the
module is bound to the demo environment.

#### Scenario: Trading is attempted outside demo

- **WHEN** the module is configured against any environment other than demo
- **THEN** it does not start, so no trading operation is reachable
