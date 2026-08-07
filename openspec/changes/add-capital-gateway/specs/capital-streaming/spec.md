## Purpose

The live feed: what a consumer receives over a WebSocket while a market moves, including the
candle that has not closed yet, and what happens to that feed when the provider's connection
drops.

## ADDED Requirements

### Requirement: A consumer subscribes by symbol and resolution

The module SHALL accept WebSocket subscriptions naming a symbol and a candle resolution, and
SHALL deliver only messages for that pair.

#### Scenario: Subscribing

- **WHEN** a consumer opens a stream for a symbol and resolution
- **THEN** it receives a status message once the upstream feed is live
- **AND** every subsequent message concerns that symbol and resolution

#### Scenario: Subscribing without a symbol

- **WHEN** a consumer opens a stream naming no symbol
- **THEN** the module refuses the connection

### Requirement: The stream carries candles and quotes

The module SHALL publish two message kinds carrying data: a candle, marked as either forming or
settled, and a quote carrying bid and ask. It SHALL also publish status and error messages. No
message SHALL expose the provider's own message shape or its tokens.

#### Scenario: A candle closes

- **WHEN** the provider reports a closed candle
- **THEN** the module publishes a candle message marked settled, carrying open, high, low, close
  and the candle's start time

#### Scenario: The market moves inside a candle

- **WHEN** a quote arrives between candle closes
- **THEN** the module publishes a quote message carrying bid, ask and timestamp

#### Scenario: The provider reports a fault

- **WHEN** the upstream connection or subscription fails
- **THEN** the module publishes an error message stating what failed, without provider
  credentials in it

### Requirement: The forming candle is assembled by the module

The provider reports a candle only when it closes, so between closes a consumer would see no
candle at all. The module SHALL assemble the candle in progress from quotes: the first quote in
a period opens it, later quotes extend its high and low and move its close. A closed candle from
the provider is authoritative and SHALL replace the assembled one.

#### Scenario: The first quote of a new period

- **WHEN** a quote arrives whose timestamp falls in a period later than the current candle
- **THEN** the module publishes a forming candle opening at that price

#### Scenario: Quotes inside the period

- **WHEN** further quotes arrive in the same period
- **THEN** the module publishes the forming candle with its high and low extended and its close
  moved to the latest price

#### Scenario: The provider's candle arrives

- **WHEN** the provider reports the closed candle for a period the module was assembling
- **THEN** the provider's values replace the assembled ones and the candle is published as
  settled

#### Scenario: A resolution with no fixed period boundary

- **WHEN** the resolution is daily or weekly, whose boundary depends on the venue's session
  rather than on the clock
- **THEN** quotes extend the last known candle instead of opening a new one, and the boundary is
  set only by the provider's closed candle

#### Scenario: A subscriber joins mid-period

- **WHEN** a consumer subscribes partway through a period
- **THEN** the forming candle it receives reflects only quotes seen since the module connected,
  and the module states that the candle is forming rather than final

### Requirement: One upstream connection serves every subscriber of a pair

The module SHALL hold at most one provider connection per symbol and resolution, shared by all
consumers of that pair, and SHALL close it once the last consumer leaves.

#### Scenario: A second consumer joins

- **WHEN** a second consumer subscribes to a symbol and resolution already streaming
- **THEN** no additional provider connection is opened
- **AND** both consumers receive the same messages

#### Scenario: The last consumer leaves

- **WHEN** the final consumer of a symbol and resolution disconnects
- **THEN** the module closes the provider connection for that pair

### Requirement: The feed survives an interruption

The module SHALL keep the provider connection alive while subscribers remain, and SHALL restore
it after a drop without the consumer reconnecting.

#### Scenario: The provider connection drops

- **WHEN** the upstream connection closes while consumers are still subscribed
- **THEN** the module publishes a status message stating it is reconnecting, reconnects, and
  resumes publishing without the consumer having to reconnect

#### Scenario: An idle feed

- **WHEN** no message has been exchanged with the provider for longer than the provider tolerates
- **THEN** the module keeps the connection alive on its own

### Requirement: A price side matching history

Candles published on the stream SHALL use the same price side as candles served from history.
Where the provider reports both sides of a closed candle, only one SHALL be published.

#### Scenario: Both price sides are reported

- **WHEN** the provider reports the same closed candle twice, once per price side
- **THEN** the module publishes exactly one candle for that period, on the same side its history
  uses
