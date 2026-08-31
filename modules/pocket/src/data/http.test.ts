import { afterEach, describe, expect, it, vi } from "vitest";
import { ArchiveError, jsonClient } from "./http";
import { noIdentity, SignedOut, type Identity } from "../auth/identity";

function signedIn(tokens: string[]): Identity {
  const queue = [...tokens];
  return {
    ...noIdentity,
    state: () => "signed-in",
    token: async () => queue[0] ?? null,
    refresh: async () => {
      queue.shift();
      if (queue.length === 0) throw new SignedOut();
      return queue[0];
    },
  };
}

const responding = (...statuses: number[]) => {
  const queue = [...statuses];
  return vi.fn(async () => new Response("{}", { status: queue.shift() ?? 200 }));
};

afterEach(() => vi.unstubAllGlobals());

function authorizationOf(fetching: ReturnType<typeof responding>, call: number): string | undefined {
  const [, init] = fetching.mock.calls[call] as unknown as [string, RequestInit];
  return (init.headers as Record<string, string>).Authorization;
}

describe("the credential a request carries", () => {
  it("is none at all when no identity is configured", async () => {
    const fetching = responding(200);
    vi.stubGlobal("fetch", fetching);

    await jsonClient("archive", {}).json("/events", { signal: new AbortController().signal });

    expect(authorizationOf(fetching, 0)).toBeUndefined();
  });

  it("is the operator's token when one is", async () => {
    const fetching = responding(200);
    vi.stubGlobal("fetch", fetching);

    await jsonClient("archive", {}, signedIn(["first"])).json("/events", {
      signal: new AbortController().signal,
    });

    expect(authorizationOf(fetching, 0)).toBe("Bearer first");
  });
});

describe("a 401", () => {
  it("is retried once with a renewed token, because one can expire in flight", async () => {
    const fetching = responding(401, 200);
    vi.stubGlobal("fetch", fetching);

    await jsonClient("archive", {}, signedIn(["stale", "fresh"])).json("/events", {
      signal: new AbortController().signal,
    });

    expect(fetching).toHaveBeenCalledTimes(2);
    expect(authorizationOf(fetching, 1)).toBe("Bearer fresh");
  });

  it("is the session and not the token once the renewal has been refused too", async () => {
    const fetching = responding(401, 401);
    vi.stubGlobal("fetch", fetching);

    const failure = await jsonClient("archive", {}, signedIn(["stale", "fresh"]))
      .json("/events", { signal: new AbortController().signal })
      .catch((cause: unknown) => cause);

    expect((failure as ArchiveError).kind).toBe("unauthenticated");
    // Twice, never three times: "refused, renew, refused" must not become a loop against both the
    // archive and the token endpoint.
    expect(fetching).toHaveBeenCalledTimes(2);
  });
});
