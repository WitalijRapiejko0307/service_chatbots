import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChannelBinding } from "@/lib/types/channel";
import { StatusBadge } from "./StatusBadge";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

const baseBinding: ChannelBinding = {
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

describe("StatusBadge", () => {
  it("shows not connected when binding is missing", () => {
    render(<StatusBadge />);
    expect(screen.getByText("statusNotConnected")).toBeInTheDocument();
  });

  it("shows connected for active verified binding", () => {
    render(<StatusBadge binding={baseBinding} channelType="telegram" />);
    expect(screen.getByText("statusConnected")).toBeInTheDocument();
  });

  it("shows pending access when flagged without binding", () => {
    render(<StatusBadge pendingAccess />);
    expect(screen.getByText("statusPendingAccess")).toBeInTheDocument();
  });

  it("shows inactive for disabled binding", () => {
    render(
      <StatusBadge
        binding={{ ...baseBinding, is_active: false }}
        channelType="telegram"
      />
    );
    expect(screen.getByText("statusInactive")).toBeInTheDocument();
  });
});
