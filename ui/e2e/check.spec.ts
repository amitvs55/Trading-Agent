import path from "node:path";
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

test("check a contract: verdict, money, evidence, what-if and a paper trade", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page);
  await page.getByRole("link", { name: "Check", exact: true }).filter({ visible: true }).first().click();
  await expect(page.getByRole("heading", { name: "Option Check" })).toBeVisible();

  // A typo gets the problem and real strikes to pick from
  const box = page.locator("#check-contract");
  await box.fill("nifty 25010 ce");
  await expect(page.locator("#check-contract-status")).toContainText("isn't a listed strike");
  await page.getByRole("button", { name: /NIFTY .* 25000 CE/ }).first().click();
  await expect(page.locator("#check-contract-status")).toContainText("lot 65");

  await page.getByRole("button", { name: "Check", exact: true }).click();
  const verdict = page.getByRole("region", { name: "Verdict" });
  await expect(verdict).toBeVisible({ timeout: 60_000 });
  await expect(verdict.getByRole("status")).toContainText(/Worth taking|Marginal|Avoid/);
  await expect(page.getByText("MOST YOU CAN LOSE", { exact: true })).toBeVisible();
  await expect(page.getByText("MARKET VIEW", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: /Profit or loss across NIFTY levels/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Scenarios" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Assumptions" })).toBeVisible();
  await expect(page).toHaveURL(/\/check\?id=/);

  // What-if: more volatility while holding changes the market view's expected P&L, without moving anything
  await page.evaluate(() => {
    const w = window as unknown as { __cls: number };
    w.__cls = 0;
    new PerformanceObserver(list => {
      for (const e of list.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) w.__cls += e.value;
    }).observe({ type: "layout-shift", buffered: false });
  });
  const odds = page.getByRole("region", { name: "Chances and expected profit or loss" });
  const before = await odds.innerText();
  const iv = page.getByLabel("Volatility change while you hold");
  await iv.focus();
  for (let i = 0; i < 6; i++) await page.keyboard.press("ArrowRight");
  await expect(page.getByText("+3.0 pts")).toBeVisible();
  await expect.poll(() => odds.innerText(), { timeout: 10_000 }).not.toBe(before);
  expect(await page.evaluate(() => (window as unknown as { __cls: number }).__cls)).toBeLessThan(0.01);

  // Follow it as a paper trade, then close it
  await page.getByRole("button", { name: "Follow as paper trade" }).click();
  await expect(page.getByRole("region", { name: "Paper trade" })).toContainText("Following");
  await page.getByRole("button", { name: "Close at the bid" }).click();
  await expect(page.getByRole("region", { name: "Paper trade" })).toContainText("Closed at");

  // It's in the list, and the page is accessible
  await expect(page.getByRole("region", { name: "Your recent checks" }).getByRole("button").first()).toBeVisible();
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.filter(v => v.impact === "serious" || v.impact === "critical")
    .map(v => `${v.id}: ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
  await page.screenshot({ path: path.join(__dirname, ".data", `check-${test.info().project.name}.png`), fullPage: true });

  // Reloading the link opens the same check
  await page.reload();
  await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible({ timeout: 30_000 });
});
