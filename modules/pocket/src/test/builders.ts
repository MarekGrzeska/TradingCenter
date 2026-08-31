import type { Market, Outcome, TrackedEvent } from "../polymarket/api";

/** Data a test states one field of. Everything a test does not name is a default that is true rather
 *  than empty, so an assertion never depends on a value the test did not write down. */

export function anOutcome(overrides: Partial<Outcome> = {}): Outcome {
  return {
    id: 1,
    name: "Yes",
    price: 0.62,
    priceAt: new Date("2026-08-31T09:00:00Z"),
    ...overrides,
  };
}

export function aMarket(overrides: Partial<Market> = {}): Market {
  return {
    id: 10,
    question: "Will it happen?",
    label: null,
    negRisk: false,
    resolvedOutcome: null,
    outcomes: [anOutcome(), anOutcome({ id: 2, name: "No", price: 0.38 })],
    ...overrides,
  };
}

export function anEvent(overrides: Partial<TrackedEvent> = {}): TrackedEvent {
  return {
    id: 100,
    providerEventId: "evt-100",
    slug: "will-it-happen",
    title: "Will it happen",
    url: "https://polymarket.com/event/will-it-happen",
    group: null,
    collection: {
      state: "collecting",
      lastSampleAt: new Date("2026-08-31T09:00:00Z"),
      reason: null,
    },
    markets: [aMarket()],
    ...overrides,
  };
}
