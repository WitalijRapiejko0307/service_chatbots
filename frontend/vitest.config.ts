import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["{app,components,lib}/**/*.test.{ts,tsx}"],
    exclude: [
      "node_modules",
      "node_modules.broken-root-owned",
      ".next",
      "e2e",
      "out",
      "build",
    ],
    coverage: {
      provider: "v8",
      reportsDirectory: "./coverage",
      exclude: ["node_modules", ".next", "e2e", "**/*.test.{ts,tsx}"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
