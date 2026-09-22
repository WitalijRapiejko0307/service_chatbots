import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Message } from "@/lib/types/message";

const { getMessages } = vi.hoisted(() => ({
  getMessages: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getMessages,
    },
  };
});

import { ApiError } from "@/lib/api";
import { useMessages } from "./useMessages";

const sampleMessages: Message[] = [
  {
    message_id: "m1",
    conversation_id: "conv-1",
    agent_id: "agent-1",
    role: "user",
    content: "Hello",
    timestamp: "2026-01-01T00:00:00Z",
  },
];

describe("useMessages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMessages.mockResolvedValue(sampleMessages);
  });

  it("loads messages for a conversation on mount", async () => {
    const { result } = renderHook(() => useMessages("conv-1"));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(getMessages).toHaveBeenCalledWith("conv-1");
    expect(result.current.messages).toEqual(sampleMessages);
    expect(result.current.error).toBeNull();
  });

  it("does not fetch when conversationId is null", async () => {
    const { result } = renderHook(() => useMessages(null));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(getMessages).not.toHaveBeenCalled();
    expect(result.current.messages).toEqual([]);
  });

  it("sets error message from ApiError on initial load failure", async () => {
    getMessages.mockRejectedValueOnce(new ApiError("404", "Conversation not found"));

    const { result } = renderHook(() => useMessages("missing"));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBe("Conversation not found");
    expect(result.current.messages).toEqual([]);
  });

  it("normalizes non-array API responses to an empty list", async () => {
    getMessages.mockResolvedValueOnce(null);

    const { result } = renderHook(() => useMessages("conv-1"));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.messages).toEqual([]);
  });

  it("refresh reloads messages", async () => {
    const { result } = renderHook(() => useMessages("conv-1"));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    getMessages.mockResolvedValueOnce([
      ...sampleMessages,
      {
        ...sampleMessages[0],
        message_id: "m2",
        content: "Follow-up",
      },
    ]);

    await result.current.refresh();

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(2);
    });
  });
});
