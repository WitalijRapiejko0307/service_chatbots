import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ChannelBinding,
  ChannelConfig,
  ChannelSupportMatrix,
} from "@/lib/types/channel";

const { listChannelBindings, getChannelConfig, getChannelSupportMatrix } = vi.hoisted(() => ({
  listChannelBindings: vi.fn(),
  getChannelConfig: vi.fn(),
  getChannelSupportMatrix: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    listChannelBindings,
    getChannelConfig,
    getChannelSupportMatrix,
  },
  ApiError: class ApiError extends Error {
    constructor(message: string) {
      super(message);
      this.name = "ApiError";
    }
  },
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

import { useChannelBindings } from "./useChannelBindings";

const sampleBinding: ChannelBinding = {
  binding_id: "bind-1",
  agent_id: "agent-1",
  channel_type: "telegram",
  channel_account_id: "123",
  is_active: true,
  is_verified: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  metadata: {},
};

const sampleConfig: ChannelConfig = {
  app_url: "https://app.example.com",
  instagram_webhook_url: "https://app.example.com/api/v1/instagram/webhook",
  instagram_verify_token: "verify-token",
  instagram_app_secret_configured: false,
  telegram_webhook_base: "https://app.example.com/api/v1/telegram/webhook",
  viber_webhook_base: "https://app.example.com/api/v1/viber/webhook",
  tiktok_webhook_base: "https://app.example.com/api/v1/tiktok/webhook",
};

const sampleMatrix: ChannelSupportMatrix = {
  channels: ["telegram"],
  capabilities: ["text_in"],
  matrix: {
    telegram: {
      text_in: "yes",
      text_out: "yes",
      images: "yes",
      media_other: "limited",
      quick_replies: "no",
      typing: "yes",
      restart_command: "yes",
      proactive_first_message: "no",
      response_window: "none",
      human_handoff: "yes",
      notes: "telegram_media_and_commands",
    },
  },
};

describe("useChannelBindings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/admin/agents/agent-1/channels");
    listChannelBindings.mockResolvedValue([sampleBinding]);
    getChannelConfig.mockResolvedValue(sampleConfig);
    getChannelSupportMatrix.mockResolvedValue(sampleMatrix);
  });

  it("loads bindings, config, and matrix on mount", async () => {
    const { result } = renderHook(() => useChannelBindings("agent-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(listChannelBindings).toHaveBeenCalledWith("agent-1", undefined, false);
    expect(result.current.bindings).toEqual([sampleBinding]);
    expect(result.current.config).toEqual(sampleConfig);
    expect(result.current.matrix).toEqual(sampleMatrix);
    expect(result.current.error).toBeNull();
    expect(result.current.appBase).toBe("https://app.example.com");
  });

  it("sets error when bindings request fails", async () => {
    listChannelBindings.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useChannelBindings("agent-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("loadError");
    expect(result.current.bindings).toEqual([]);
  });

  it("handles OAuth return query params and cleans the URL", async () => {
    window.history.replaceState(
      null,
      "",
      "/admin/agents/agent-1/channels?tiktok_error=1&keep=1#section"
    );

    const replaceStateSpy = vi.spyOn(window.history, "replaceState");

    const { result } = renderHook(() => useChannelBindings("agent-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("oauthReturnError");
    expect(replaceStateSpy).toHaveBeenCalledWith(
      null,
      "",
      "/admin/agents/agent-1/channels?keep=1#section"
    );
  });

  it("sets instagram oauth error from query params", async () => {
    window.history.replaceState(
      null,
      "",
      "/admin/agents/agent-1/channels?instagram_error=1"
    );

    const { result } = renderHook(() => useChannelBindings("agent-1"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("instagram.oauthReturnError");
  });
});
