import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const VIEWER = { user: "e2e-viewer", pw: process.env.E2E_VIEWER_PW! };

async function signIn(page: Page) {
  await page.goto("/signals");
  await page.getByLabel("USERNAME").fill(VIEWER.user);
  await page.getByLabel("PASSWORD").fill(VIEWER.pw);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Live Signals" })).toBeVisible();
}

test("price an order with its charges, place it, see it in Orders and cancel it", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);
  await page.getByRole("link", { name: "Trade", exact: true }).filter({ visible: true }).first().click();
  await expect(page.getByRole("heading", { name: "Trade" })).toBeVisible();

  await page.locator("#desk-contract").fill("nifty 25000 ce");
  await expect(page.locator("#desk-contract-status")).toContainText("lot 65");
  await page.getByRole("button", { name: "Limit", exact: true }).click();
  const price = page.getByLabel("LIMIT PRICE");
  await expect(price).not.toHaveValue("");                           // starts from the price on your side of the book
  await price.fill("50.00");

  const ticket = page.getByRole("form", { name: "Order ticket" });
  await expect(ticket.getByText("Order value")).toBeVisible();
  await expect(ticket).toContainText("₹3,250");                       // 65 × ₹50
  await ticket.getByRole("button", { name: "Charges incl. GST" }).click();
  await expect(ticket.getByText("Brokerage (₹20 an order)")).toBeVisible();
  await expect(ticket.getByText("GST 18%")).toBeVisible();
  await expect(ticket.getByText("Breakeven")).toBeVisible();

  const a11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(a11y.violations.filter(v => v.impact === "serious" || v.impact === "critical")
    .map(v => `${v.id}: ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);

  // With the market closed it waits for the open; in market hours, with no live feed here, it is refused
  await ticket.getByRole("button", { name: /^Buy 1 lot/ }).click();
  const outcome = ticket.getByRole("status").or(ticket.getByRole("alert"));
  await expect(outcome.first()).toContainText(/after-market order placed|aren't streaming/);
  if (await ticket.getByRole("status").filter({ hasText: "after-market order placed" }).isVisible()) {
    await page.getByRole("tab", { name: /Orders/ }).click();
    await expect(page.getByText("AFTER-MARKET").first()).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).first().click();
    await expect(page.getByText("CANCELLED").first()).toBeVisible();
  }
});

test("selling what you don't hold is explained, not allowed", async ({ page }) => {
  await signIn(page);
  await page.goto("/trade");
  await page.locator("#desk-contract").fill("nifty 25000 pe");
  await expect(page.locator("#desk-contract-status")).toContainText("lot 65");
  await page.getByRole("group", { name: "Buy or sell" }).getByRole("button", { name: /^Sell/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: "buy-only" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sell 1 lot/ })).toBeDisabled();
});
