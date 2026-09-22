import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Conversation } from "@/lib/types/conversation";

const { getAdminConversation } = vi.hoisted(() => ({
  getAdminConversation: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getAdminConversation,
    },
  };
});

import { ApiError } from "@/lib/api";
import { useAdminConversation } from "./useAdminConversation";

const sampleConversation: Conversation = {
  conversation_id: "conv-1",
  agent_id: "agent-1",
  status: "AI_ACTIVE",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T01:00:00Z",
};

describe("useAdminConversation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAdminConversation.mockResolvedValue(sampleConversation);
  });

  it("loads conversation on mount", async () => {
    const { result } = renderHook(() => useAdminConversation("conv-1"));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(getAdminConversation).toHaveBeenCalledWith("conv-1");
    expect(result.current.conversation).toEqual(sampleConversation);
    expect(result.current.error).toBeNull();
  });

  it("skips loading when conversationId is null", async () => {
    const { result } = renderHook(() => useAdminConversation(null));

    expect(result.current.conversation).toBeNull();
    expect(getAdminConversation).not.toHaveBeenCalled();
  });

  it("surfaces ApiError message on failure", async () => {
    getAdminConversation.mockRejectedValueOnce(new ApiError("403", "Forbidden"));

    const { result } = renderHook(() => useAdminConversation("conv-1"));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBe("Forbidden");
    expect(result.current.conversation).toBeNull();
  });

  it("refresh reloads conversation data", async () => {
    const { result } = renderHook(() => useAdminConversation("conv-1"));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const updated: Conversation = {
      ...sampleConversation,
      status: "HUMAN_ACTIVE",
    };
    getAdminConversation.mockResolvedValueOnce(updated);

    await result.current.refresh();

    await waitFor(() => {
      expect(result.current.conversation?.status).toBe("HUMAN_ACTIVE");
    });
  });
});
