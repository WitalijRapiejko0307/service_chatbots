import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getAdminToken, setAdminToken } from "./auth";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

import { api, ApiError } from "./api";

const API_BASE = "https://api.test.example";

function jsonResponse(
  body: unknown,
  init: { status?: number; statusText?: string; contentType?: string | null } = {}
) {
  const { status = 200, statusText = "OK", contentType = "application/json" } = init;
  const headers = new Map<string, string>();
  if (contentType) {
    headers.set("content-type", contentType);
  }

  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    headers: {
      get: (name: string) => headers.get(name.toLowerCase()) ?? null,
    },
    json: vi.fn(async () => body),
  };
}

function textResponse(
  text: string,
  init: { status?: number; statusText?: string } = {}
) {
  const { status = 200, statusText = "OK" } = init;
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    headers: {
      get: () => null,
    },
    json: vi.fn(async () => {
      throw new SyntaxError("Unexpected token");
    }),
    text: vi.fn(async () => text),
  };
}

describe("api request transport", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    localStorage.clear();
    vi.stubEnv("NEXT_PUBLIC_API_URL", API_BASE);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("performs successful GET with JSON body and default headers", async () => {
    const agent = { agent_id: "a1", config: {}, is_active: true };
    fetchMock.mockResolvedValueOnce(jsonResponse(agent));

    const result = await api.getAgent("a1");

    expect(result).toEqual(agent);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API_BASE}/api/v1/agents/a1`);
    expect(init.method).toBeUndefined();
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
    });
    expect(init.headers).not.toHaveProperty("Authorization");
  });

  it("uses NEXT_PUBLIC_API_URL without trailing slash", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com/");
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await api.listAgents(false);

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("https://api.example.com/api/v1/agents/?active_only=false");
  });

  it("adds Authorization header when requireAuth is true and token exists", async () => {
    setAdminToken("secret-token");
    fetchMock.mockResolvedValueOnce(jsonResponse({ agent_id: "x", config: {} }));

    await api.createAgent("x", { name: "Bot" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({
      Authorization: "Bearer secret-token",
      "Content-Type": "application/json",
    });
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      agent_id: "x",
      config: { name: "Bot" },
    });
  });

  it("omits Authorization when requireAuth is true but token is missing", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await api.listConversations();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(init.headers).not.toHaveProperty("Authorization");
    expect(getAdminToken()).toBeNull();
  });

  it("returns undefined for 204 No Content without parsing JSON", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(null, { status: 204, contentType: null }));

    const result = await api.deleteAgent("agent-1");

    expect(result).toBeUndefined();
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("DELETE");
  });

  it("parses JSON for 201 Created when content-type is application/json", async () => {
    const created = { conversation_id: "c1", status: "AI_ACTIVE" };
    fetchMock.mockResolvedValueOnce(jsonResponse(created, { status: 201 }));

    const result = await api.createConversation({ agent_id: "a1" });

    expect(result).toEqual(created);
  });

  it("returns undefined for 201 Created without JSON content-type", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(null, { status: 201, contentType: "text/plain" })
    );

    const result = await api.createConversation({ agent_id: "a1" });

    expect(result).toBeUndefined();
  });

  it("throws ApiError with custom error payload fields", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "AGENT_NOT_FOUND",
            message: "Agent missing",
            details: { agent_id: "x" },
            request_id: "req-1",
          },
        },
        { status: 404, statusText: "Not Found" }
      )
    );

    await expect(api.getAgent("x")).rejects.toMatchObject({
      name: "ApiError",
      code: "AGENT_NOT_FOUND",
      message: "Agent missing",
      details: { agent_id: "x" },
      requestId: "req-1",
    });
  });

  it("normalizes FastAPI detail string into ApiError message", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "Not authenticated" }, { status: 401, statusText: "Unauthorized" })
    );

    try {
      await api.getAdminConversation("conv-1");
      expect.fail("expected ApiError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe("401");
      expect(apiErr.message).toBe("Not authenticated");
    }
    expect(getAdminToken()).toBeNull();
  });

  it("joins FastAPI validation detail array messages", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { detail: [{ msg: "field required" }, { msg: "invalid type" }] },
        { status: 422, statusText: "Unprocessable Entity" }
      )
    );

    await expect(api.createAgent("x", {})).rejects.toMatchObject({
      code: "422",
      message: "field required; invalid type",
    });
  });

  it("throws ApiError for non-JSON error responses", async () => {
    fetchMock.mockResolvedValueOnce(
      textResponse("Internal Server Error", {
        status: 500,
        statusText: "Internal Server Error",
      })
    );

    await expect(api.getAgent("a1")).rejects.toMatchObject({
      code: "500",
      message: "HTTP 500: Internal Server Error",
    });
  });

  it("returns undefined for successful non-JSON responses", async () => {
    fetchMock.mockResolvedValueOnce(textResponse("ok", { status: 200 }));

    const result = await api.getAgent("a1");

    expect(result).toBeUndefined();
  });

  it("wraps fetch rejection in NETWORK_ERROR ApiError", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(api.getAgent("a1")).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      message: "Failed to fetch",
    });
  });

  it("clears admin token on 403 responses", async () => {
    setAdminToken("expired");
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "Forbidden" }, { status: 403, statusText: "Forbidden" })
    );

    await expect(api.listConversations()).rejects.toBeInstanceOf(ApiError);
    expect(getAdminToken()).toBeNull();
  });

  it("serializes listConversations query parameters", async () => {
    setAdminToken("token");
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await api.listConversations({
      agent_id: "agent-1",
      status: "NEEDS_HUMAN",
      marketing_status: "NEW",
      crm_stage_id: "stage-1",
      limit: 50,
      sort_by: "updated_at",
      sort_order: "asc",
      created_from: "2026-01-01",
      created_to: "2026-01-31",
    });

    const [url] = fetchMock.mock.calls[0] as [string];
    const query = new URL(url).searchParams;
    expect(query.get("agent_id")).toBe("agent-1");
    expect(query.get("status")).toBe("NEEDS_HUMAN");
    expect(query.get("marketing_status")).toBe("NEW");
    expect(query.get("crm_stage_id")).toBe("stage-1");
    expect(query.get("limit")).toBe("50");
    expect(query.get("sort_by")).toBe("updated_at");
    expect(query.get("sort_order")).toBe("asc");
    expect(query.get("created_from")).toBe("2026-01-01");
    expect(query.get("created_to")).toBe("2026-01-31");
  });

  it("serializes getStats query parameters", async () => {
    setAdminToken("token");
    fetchMock.mockResolvedValueOnce(jsonResponse({ period: "7d", totals: {} }));

    await api.getStats({ period: "7d", include_comparison: true });

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe(
      `${API_BASE}/api/v1/admin/stats?period=7d&include_comparison=true`
    );
  });

  it("builds getMessages URL with limit query param", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await api.getMessages("conv-42", 25);

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe(`${API_BASE}/api/v1/chat/conversations/conv-42/messages?limit=25`);
  });
});

describe("ApiError", () => {
  it("exposes code, message, details, and requestId", () => {
    const err = new ApiError("VALIDATION_ERROR", "Bad input", { field: "name" }, "rid-9");

    expect(err.name).toBe("ApiError");
    expect(err.code).toBe("VALIDATION_ERROR");
    expect(err.message).toBe("Bad input");
    expect(err.details).toEqual({ field: "name" });
    expect(err.requestId).toBe("rid-9");
  });
});
