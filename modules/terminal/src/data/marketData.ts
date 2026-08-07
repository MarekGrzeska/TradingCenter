import { resolveGatewayEndpoints } from "./config";
import { createGatewaySource } from "./gatewaySource";
import type { MarketDataSource } from "./source";

/**
 * The one market-data source the app runs on. `capital-gateway` is the only
 * implementation today; the `MarketDataSource` interface stays because a candle
 * store is expected to become a second one, and it must arrive without the
 * chart, the grid or the search knowing (design.md).
 *
 * A single module-level instance, so every view shares one socket hub — that
 * sharing is what makes six charts on the same pair one connection rather than
 * six.
 */
const { httpBase, wsBase } = resolveGatewayEndpoints();

export const marketData: MarketDataSource = createGatewaySource(httpBase, wsBase);
