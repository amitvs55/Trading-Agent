import { execFileSync } from "node:child_process";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const VIEWER = { user: "e2e-viewer", pw: process.env.E2E_VIEWER_PW! };
const ROOT = path.resolve(__dirname, "..", "..");
const DB = path.join(__dirname, ".data", "e2e.db");
const PYTHON = process.env.E2E_PYTHON ?? (process.platform === "win32" ? path.join(ROOT, ".venv", "Scripts", "python.exe") : "python");

/** What the recorder does on a tick: save the levels (the e2e API reads the saved copy every 250 ms). */
function publish(nifty: number, sensex: number): number {
  const out = execFileSync(PYTHON, [path.join(__dirname, "live_tick.py"), DB, String(nifty), String(sensex)], { cwd: ROOT });
  return Number(String(out).trim().split(/\s+/).pop());        // epoch ms when it was saved
}

async function signIn(page: Page) {
  await page.goto("/signals");
  await page.getByLabel("USERNAME").fill(VIEWER.user);
  await page.getByLabel("PASSWORD").fill(VIEWER.pw);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Live Signals" })).toBeVisible();
}

test("live NIFTY 50 and SENSEX update in place without moving anything", async ({ page }) => {
  publish(23096.95, 75512.10);
  await signIn(page);
  const ticker = page.getByRole("group", { name: "Live index levels" }).filter({ visible: true });
  await expect(ticker).toHaveCount(1);
  await expect(ticker.getByRole("group", { name: "NIFTY 50 23,096.95, up 86.75 points, 0.38 percent" })).toBeVisible();
  await expect(ticker.getByRole("group", { name: /^SENSEX 75,512\.10, up 250\.30 points/ })).toBeVisible();

  // Count layout shifts from here on: a new level must not move a single pixel
  await page.evaluate(() => {
    const w = window as unknown as { __cls: number };
    w.__cls = 0;
    new PerformanceObserver(list => {
      for (const e of list.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) {
        if (!e.hadRecentInput) w.__cls += e.value;
      }
    }).observe({ type: "layout-shift", buffered: false });
  });
  const before = await ticker.boundingBox();

  const savedAt = publish(23120.5, 75590.25);
  await expect(ticker.getByRole("group", { name: /^NIFTY 50 23,120\.50, up 110\.30 points/ })).toBeVisible({ timeout: 5000 });
  const tookMs = Date.now() - savedAt;
  publish(22990.0, 75100.0);                                     // and down, below the previous close
  await expect(ticker.getByRole("group", { name: /^NIFTY 50 22,990\.00, down 20\.20 points/ })).toBeVisible({ timeout: 5000 });
  await expect(ticker.getByRole("group", { name: /^SENSEX 75,100\.00, down 161\.80 points/ })).toBeVisible();

  expect(await page.evaluate(() => (window as unknown as { __cls: number }).__cls)).toBe(0);
  expect(await ticker.boundingBox()).toEqual(before);
  // Saved → on screen. Here the API reads the saved copy every 250 ms (SQLite); on Postgres it is pushed (NOTIFY)
  expect(tookMs).toBeLessThan(1500);
  console.log(`[${test.info().project.name}] new level on screen ${tookMs} ms after it was saved`);

  // It came over the pushed stream, not the once-a-second fallback
  const status = page.locator('[title^="Live"]').filter({ visible: true }).first();
  await expect(status).toBeVisible();
  expect(await status.getAttribute("title")).not.toMatch(/unavailable/);

  // The Signals card shows spot, future and basis from the same live moment
  await expect(page.getByText("22,990.00").filter({ visible: true }).first()).toBeVisible();

  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.filter(v => v.impact === "serious" || v.impact === "critical").map(v => v.id)).toEqual([]);
  await page.screenshot({ path: path.join(__dirname, ".data", `ticker-${test.info().project.name}.png`) });
});
