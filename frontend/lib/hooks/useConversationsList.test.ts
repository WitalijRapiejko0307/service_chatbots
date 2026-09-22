import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Conversation } from "@/lib/types/conversation";

const { listConversations } = vi.hoisted(() => ({
  listConversations: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listConversations,
    },
  };
});

vi.mock("./useAdminWebSocket", () => ({
  useAdminWebSocket: () => ({
    isConnected: true,
    onConversationUpdate: () => () => {},
    onNewEscalation: () => () => {},
    onStatsUpdate: () => () => {},
  }),
}));

vi.mock("@/lib/notifications", () => ({
  showEscalationNotification: vi.fn().mockResolvedValue(undefined),
}));

import { ApiError } from "@/lib/api";
import { useConversationsList } from "./useConversationsList";

const baseConversation = (
  overrides: Partial<Conversation> & Pick<Conversation, "conversation_id" | "status">
): Conversation => ({
  agent_id: "agent-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  ...overrides,
});

describe("useConversationsList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listConversations.mockResolvedValue([
      baseConversation({ conversation_id: "c1", status: "AI_ACTIVE" }),
      baseConversation({ conversation_id: "c2", status: "NEEDS_HUMAN" }),
    ]);
  });

  it("loads conversations with filter params on mount", async () => {
    const { result } = renderHook(() =>
      useConversationsList({
        filter: "needs_attention",
        agentId: "agent-1",
        enablePolling: false,
      })
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(listConversations).toHaveBeenCalledWith(
      expect.objectContaining({
        agent_id: "agent-1",
        status: "NEEDS_HUMAN",
        limit: 100,
        sort_by: "created_at",
        sort_order: "desc",
      })
    );
    expect(result.current.conversations).toHaveLength(2);
    expect(result.current.needsHumanCount).toBe(1);
    expect(result.current.error).toBeNull();
  });

  it("client-filters active conversations", async () => {
    listConversations.mockResolvedValue([
      baseConversation({ conversation_id: "c1", status: "AI_ACTIVE" }),
      baseConversation({ conversation_id: "c2", status: "CLOSED" }),
      baseConversation({ conversation_id: "c3", status: "HUMAN_ACTIVE" }),
    ]);

    const { result } = renderHook(() =>
      useConversationsList({ filter: "active", enablePolling: false })
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.conversations.map((c) => c.conversation_id)).toEqual(["c1", "c3"]);
  });

  it("sets error from ApiError message", async () => {
    listConversations.mockRejectedValueOnce(new ApiError("500", "Server error"));

    const { result } = renderHook(() =>
      useConversationsList({ enablePolling: false })
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBe("Server error");
    expect(result.current.conversations).toEqual([]);
  });

  it("passes date range filters to the API", async () => {
    const { result } = renderHook(() =>
      useConversationsList({
        createdFrom: "2026-01-01",
        createdTo: "2026-01-31",
        enablePolling: false,
      })
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(listConversations).toHaveBeenCalledWith(
      expect.objectContaining({
        created_from: "2026-01-01",
        created_to: "2026-01-31",
      })
    );
  });
});
