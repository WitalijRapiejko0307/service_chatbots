import { describe, expect, it } from "vitest";

import {
  DEFAULT_EXAMPLES,
  generateAgentId,
  generateDefaultConfig,
} from "./agentConfig";

describe("generateDefaultConfig", () => {
  it("returns stable defaults for a new agent form", () => {
    const config = generateDefaultConfig();

    expect(config.rag_enabled).toBe(false);
    expect(config.languages).toEqual(["ru", "en"]);
    expect(config.examples).toEqual(DEFAULT_EXAMPLES);
    expect(config.workflow_enabled).toBe(false);
    expect(config.llm_model).toBe("gpt-4o-mini");
  });
});

describe("generateAgentId", () => {
  it("transliterates Cyrillic and normalizes to snake_case", () => {
    expect(generateAgentId("Клиника", "Иванов")).toBe("klinika_ivanov");
  });

  it("handles Latin names without person suffix", () => {
    expect(generateAgentId("Acme Corp")).toBe("acme_corp");
  });
});
