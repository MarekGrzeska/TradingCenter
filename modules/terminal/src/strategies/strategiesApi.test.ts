import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse, setupServer } from "../test/httpDouble";
import { createStrategiesApi, Refused, SaveConflict } from "./strategiesApi";

/**
 * The wire↔domain seam. What fails quietly here is a save that collided being read as a plain failure — so the editor
 * would not offer the newer revision — and a refusal's problems flattened to a sentence with no place to mark.
 */

const BASE = "http://strategies.test";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const signal = () => new AbortController().signal;

describe("createStrategiesApi", () => {
  it("reads a save that came too late as a conflict naming the latest revision", async () => {
    server.use(
      http.post(`${BASE}/strategies/7/revisions`, () =>
        HttpResponse.json({ detail: "revision 5 was saved after the one this change was made to", latest_revision: 5 }, { status: 409 }),
      ),
    );

    const saving = createStrategiesApi(BASE).save(7, {}, 4, signal());

    await expect(saving).rejects.toBeInstanceOf(SaveConflict);
    await expect(saving).rejects.toMatchObject({ latest: 5 });
  });

  it("keeps every problem of a refused document with its place", async () => {
    const problems = [{ path: "entries[0].when", message: "unknown function", column: 9, hint: "ema" }];
    server.use(
      http.post(`${BASE}/strategies`, () =>
        HttpResponse.json({ detail: "the document is not a valid strategy", problems }, { status: 422 }),
      ),
    );

    const creating = createStrategiesApi(BASE).create({}, signal());

    await expect(creating).rejects.toBeInstanceOf(Refused);
    await expect(creating).rejects.toMatchObject({ problems });
  });
});
