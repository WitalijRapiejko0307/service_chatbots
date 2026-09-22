import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import {
  getUserFriendlyMessage,
  handleApiError,
  logError,
  type ErrorInfo,
} from "./errorHandler";

describe("handleApiError", () => {
  it("maps ApiError to ErrorInfo", () => {
    const err = new ApiError("AGENT_NOT_FOUND", "Missing agent", { id: "a1" }, "req-1");

    expect(handleApiError(err)).toEqual({
      code: "AGENT_NOT_FOUND",
      message: "Missing agent",
      details: { id: "a1" },
      requestId: "req-1",
    });
  });

  it("maps generic Error to UNKNOWN_ERROR", () => {
    expect(handleApiError(new Error("boom"))).toEqual({
      code: "UNKNOWN_ERROR",
      message: "boom",
    });
  });

  it("maps non-Error values to a generic message", () => {
    expect(handleApiError(null)).toEqual({
      code: "UNKNOWN_ERROR",
      message: "An unexpected error occurred",
    });
  });
});

describe("getUserFriendlyMessage", () => {
  it("returns mapped message for known codes", () => {
    const info: ErrorInfo = { code: "NETWORK_ERROR", message: "raw" };
    expect(getUserFriendlyMessage(info)).toBe(
      "Network error. Please check your connection and try again."
    );
  });

  it("falls back to error.message when code is unknown", () => {
    expect(getUserFriendlyMessage({ code: "CUSTOM", message: "Custom failure" })).toBe(
      "Custom failure"
    );
  });

  it("uses default text when message is empty", () => {
    expect(getUserFriendlyMessage({ code: "CUSTOM", message: "" })).toBe(
      "An error occurred. Please try again."
    );
  });
});

describe("logError", () => {
  it("logs structured error info", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    logError({ code: "X", message: "m" }, "Stats");

    expect(spy).toHaveBeenCalledWith("[Stats]", {
      code: "X",
      message: "m",
      details: undefined,
      requestId: undefined,
    });

    spy.mockRestore();
  });
});
