## Purpose

Holds the module's connection to capital.com: how it authenticates, how long that
authentication lasts, which environment it is allowed to reach, and which trading account
subsequent calls act on.

## ADDED Requirements

### Requirement: Credentials never leave the module

The module SHALL authenticate to capital.com on behalf of every caller. Provider credentials
and session tokens SHALL NOT appear in any response, in any WebSocket message, or in any log
line.

#### Scenario: A caller reads data without holding a credential

- **WHEN** a consumer calls any endpoint of this module
- **THEN** it supplies no capital.com credential
- **AND** the response carries no API key, identifier, password, `CST` or `X-SECURITY-TOKEN`

#### Scenario: Credentials are missing at startup

- **WHEN** the module starts without an API key, identifier or password configured
- **THEN** it refuses to start and names which value is missing

### Requirement: Demo environment only

The module SHALL refuse to operate against any capital.com host other than the demo host. The
check SHALL happen at startup, before any request is issued.

#### Scenario: Configured for the live host

- **WHEN** the configured base URL or streaming URL is not the demo host
- **THEN** the module refuses to start and states that only the demo environment is permitted

#### Scenario: Published capability states the environment

- **WHEN** a consumer reads the module's capabilities
- **THEN** the response names the environment as `demo`

### Requirement: Sessions are renewed without the caller noticing

A capital.com session expires after roughly ten idle minutes. The module SHALL renew it
transparently, and a concurrent burst of calls SHALL cause at most one login.

#### Scenario: An expired session is met mid-call

- **WHEN** the provider rejects a request because the session expired
- **THEN** the module logs in again and retries the request once
- **AND** the caller receives the result of the retry, not the rejection

#### Scenario: Several calls arrive with no valid session

- **WHEN** multiple requests need a session at the same moment
- **THEN** exactly one login is issued and all of them proceed on it

### Requirement: Accounts are listed and one is active

The module SHALL publish the accounts reachable with the configured credentials, mark which one
is active, and allow switching the active account. Trading and position reads SHALL act on the
active account.

#### Scenario: Listing accounts

- **WHEN** a consumer lists accounts
- **THEN** each account carries its identifier, name, currency, balance, available funds and
  profit or loss
- **AND** exactly one is marked active

#### Scenario: Switching the active account

- **WHEN** a consumer switches to a known account identifier
- **THEN** the module returns that account marked active
- **AND** subsequent position and order operations act on it

#### Scenario: Switching to an unknown account

- **WHEN** a consumer switches to an identifier the provider does not accept
- **THEN** the module answers with a client error naming the rejected identifier
- **AND** the previously active account remains active

### Requirement: The module publishes what it can do

The module SHALL publish a machine-readable statement of its capabilities: the provider, the
environment, which order types it accepts, and whether it streams.

#### Scenario: Reading capabilities

- **WHEN** a consumer reads the capabilities
- **THEN** the response states provider `capital.com`, environment `demo`, streaming available,
  and the accepted order types
