/** Public API / WebSocket origins for split frontend + API deploys. */

function trimTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

function isLocalhostHost(host: string): boolean {
  return host === "localhost:3000" || host.startsWith("localhost:");
}

function httpToWs(url: string): string | null {
  if (url.startsWith("https://")) return `wss://${url.slice("https://".length)}`;
  if (url.startsWith("http://")) return `ws://${url.slice("http://".length)}`;
  return null;
}

/**
 * Base URL for REST calls (`https://api.example.com` or `""` for same-origin).
 *
 * `NEXT_PUBLIC_API_URL` wins when set (Railway: two public domains).
 * Otherwise localhost → `http://localhost:8000`, other hosts → relative URLs
 * (nginx / ALB same-origin).
 */
export function getApiBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (explicit) return trimTrailingSlash(explicit);

  if (typeof window !== "undefined" && window.location) {
    if (isLocalhostHost(window.location.host)) {
      return "http://localhost:8000";
    }
    return "";
  }

  if (process.env.NODE_ENV === "production") {
    return "";
  }

  return "http://localhost:8000";
}

/**
 * Base URL for WebSocket connections (`wss://api.example.com`).
 *
 * Prefers `NEXT_PUBLIC_WS_URL`, then derives `ws`/`wss` from `NEXT_PUBLIC_API_URL`.
 */
export function getWebSocketBaseUrl(): string {
  const explicitWs = process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (explicitWs) return trimTrailingSlash(explicitWs);

  const explicitApi = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (explicitApi) {
    const converted = httpToWs(trimTrailingSlash(explicitApi));
    if (converted) return converted;
  }

  if (typeof window !== "undefined" && window.location) {
    if (isLocalhostHost(window.location.host)) {
      return "ws://localhost:8000";
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }

  return "ws://localhost:8000";
}
