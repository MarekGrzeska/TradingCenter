/** FNV-1a — a small, well-known 32-bit string hash. Only used to turn a
 *  symbol/resolution pair into a PRNG seed; no cryptographic property needed. */
export function hashString(input: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** mulberry32 — a tiny, fast, deterministic PRNG. Same seed, same sequence,
 *  forever: that determinism is the entire point of the mock source (task 3.6,
 *  "test na powtarzalności serii"). Not for anything security-sensitive. */
export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
