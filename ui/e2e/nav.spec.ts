import { expect, test, type Page } from "@playwright/test";

const ADMIN = { user: "e2e-admin", pw: process.env.E2E_ADMIN_PW! };
const VIEWER = { user: "e2e-viewer", pw: process.env.E2E_VIEWER_PW! };

// Laptops to wide monitors, including each breakpoint where the bar changes (lg 1024, xl 1280, 2xl 1536)
const WIDTHS = [1024, 1180, 1280, 1366, 1440, 1536, 1600, 1680, 1920, 2560];

async function signIn(page: Page, who: { user: string; pw: string }) {
  await page.goto("/signals");
  await page.getByLabel("USERNAME").fill(who.user);
  await page.getByLabel("PASSWORD").fill(who.pw);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Live Signals" })).toBeVisible();
}

/** Every visible link and button in the top bar: inside the bar, and the thing under the pointer at its centre. */
async function barProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const row = document.querySelector("nav > div.mx-auto") as HTMLElement;
    const out: string[] = [];
    const bar = row.getBoundingClientRect();
    for (const el of Array.from(row.querySelectorAll<HTMLElement>("a, button"))) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;                               // hidden at this width
      const name = (el.textContent || "").trim() || el.getAttribute("aria-label") || el.tagName;
      if (r.left < bar.left - 1 || r.right > Math.min(bar.right, window.innerWidth) + 1) out.push(`${name}: outside the bar`);
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      if (!hit || !(hit === el || el.contains(hit))) out.push(`${name}: covered by <${hit?.tagName.toLowerCase()} class="${hit?.getAttribute("class")?.slice(0, 60)}">`);
    }
    for (const child of Array.from(row.children) as HTMLElement[]) {
      const r = child.getBoundingClientRect();
      if (r.width && (child.scrollWidth > child.clientWidth + 1)) out.push(`a bar section overflows (${child.className.slice(0, 50)})`);
    }
    if (document.documentElement.scrollWidth > window.innerWidth) out.push("the page scrolls sideways");
    return out;
  });
}

for (const who of [ADMIN, VIEWER]) {
  test(`every top-bar link can be clicked at every desktop width (${who.user})`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "the desktop bar");
    await signIn(page, who);
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await expect.poll(() => barProblems(page), { message: `top bar at ${width}px`, timeout: 3000 }).toEqual([]);
      if (who === ADMIN && [1024, 1536, 1920].includes(width)) {
        await page.locator("nav").first().screenshot({ path: `e2e/.data/nav-${width}.png` });
      }
    }
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/performance");
    await page.locator("nav").getByRole("link", { name: "Signals", exact: true }).click();
    await expect(page).toHaveURL(/\/signals$/);
    await expect(page.getByRole("heading", { name: "Live Signals" })).toBeVisible();
  });
}
