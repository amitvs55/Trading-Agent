import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const ADMIN = { user: "e2e-admin", pw: process.env.E2E_ADMIN_PW! };
const VIEWER = { user: "e2e-viewer", pw: process.env.E2E_VIEWER_PW! };

async function signIn(page: Page, who: { user: string; pw: string }) {
  await page.goto("/signals");
  await page.getByLabel("USERNAME").fill(who.user);
  await page.getByLabel("PASSWORD").fill(who.pw);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Live Signals" })).toBeVisible();
}

/** No serious or critical WCAG 2.2 AA violations (the review's gate). */
async function expectAccessible(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const bad = result.violations.filter(v => v.impact === "serious" || v.impact === "critical");
  expect(bad.map(v => `${v.id}: ${v.nodes.length} node(s), e.g. ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
}

test("an admin signs in and sees the signal record", async ({ page }) => {
  await signIn(page, ADMIN);
  await expectAccessible(page);
  await page.goto("/performance");
  await expect(page.getByRole("heading", { name: "Track record" })).toBeVisible();
  await expect(page.getByText("NF-261016-001").filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByText("Is the edge real?")).toBeVisible();
  await expectAccessible(page);
});

test("pausing new signals shows everywhere, and resuming clears it", async ({ page }) => {
  await signIn(page, ADMIN);
  await page.goto("/operations");
  const resume = page.getByRole("button", { name: "Resume new signals" });
  await expect(resume.or(page.getByRole("button", { name: "Pause new signals" }))).toBeEnabled();
  if (await resume.isVisible()) await resume.click();                // left paused by an earlier failed run
  await page.getByRole("button", { name: "Pause new signals" }).click();
  await expect(page.getByText("New signals are paused")).toBeVisible();
  await expectAccessible(page);
  await page.goto("/signals");
  await expect(page.getByText("New signals paused").first()).toBeVisible();
  await page.goto("/operations");
  await page.getByRole("button", { name: "Resume new signals" }).click();
  await expect(page.getByText("New signals are on")).toBeVisible();
});

test("a viewer sees the signal pages but not the admin ones", async ({ page }) => {
  await signIn(page, VIEWER);
  await page.goto("/paper");
  await expect(page.getByRole("heading", { name: "Paper trading" })).toBeVisible();
  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "This page is for admins" })).toBeVisible();
});

test("an unknown address gets the branded 404", async ({ page }) => {
  await signIn(page, ADMIN);
  const res = await page.goto("/no-such-page");
  expect(res?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "This page doesn't exist" })).toBeVisible();
  await page.getByRole("link", { name: "Go to Signals" }).click();
  await expect(page.getByRole("heading", { name: "Live Signals" })).toBeVisible();
});
