import { expect, test } from "@playwright/test";

test("homepage shows main heading and admin link", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Service ChatBot" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Open admin" })).toBeVisible();
});
