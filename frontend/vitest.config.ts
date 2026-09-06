import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Unit tests for the pure parts of the frontend: the typed API client in
 * fixture mode, the fixture-mode assistant, formatting, and session storage.
 * They run in Node with no browser and no backend — anything that needs the
 * DOM is stubbed inside the test — so they are fast enough to run on every
 * change. `@/` resolves exactly as it does for Next.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    // The API client's fixture mode simulates latency; keep the tests snappy.
    testTimeout: 15_000,
  },
});
