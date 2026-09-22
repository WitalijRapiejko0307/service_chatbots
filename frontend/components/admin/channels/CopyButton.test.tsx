import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CopyButton } from "./CopyButton";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

describe("CopyButton", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
      configurable: true,
    });
  });

  it("renders copy label and is disabled without value", () => {
    render(<CopyButton value="" />);

    const button = screen.getByRole("button", { name: "copy" });
    expect(button).toBeDisabled();
  });

  it("shows copied state after successful click", async () => {
    const user = userEvent.setup();
    render(<CopyButton value="secret-webhook-url" />);

    await user.click(screen.getByRole("button", { name: "copy" }));

    expect(await screen.findByText("copied")).toBeInTheDocument();
  });
});
