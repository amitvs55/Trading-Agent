import { expect, test, type Page } from "@playwright/test";

/**
 * Layout guard for every page, both roles, phone to wide monitor: the page never scrolls sideways,
 * and every visible control is the thing under the pointer at its centre (nothing covers it) and is
 * not cut off at the screen edge. Pages are scrolled through, so controls further down count too.
 */

const ADMIN = { user: "e2e-admin", pw: process.env.E2E_ADMIN_PW! };
const VIEWER = { user: "e2e-viewer", pw: process.env.E2E_VIEWER_PW! };
const WIDTHS = [360, 390, 768, 1024, 1280, 1536, 1920];
const SIGNAL = "/signals/NF-261016-001";
const VIEWER_PAGES = ["/signals", SIGNAL, "/check", "/paper", "/performance", "/account"];
const ADMIN_PAGES = [...VIEWER_PAGES, "/agents", "/", "/history", "/usage", "/operations", "/connectors"];

async function signIn(page: Page, who: { user: string; pw: string }) {
  await page.goto("/signals");
  await page.getByLabel("USERNAME").fill(who.user);
  await page.getByLabel("PASSWORD").fill(who.pw);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Live Signals" })).toBeVisible();
}

/** Problems on the current page at the current width, checked at each scroll position. */
async function layoutProblems(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const out = new Set<string>();
    const vw = window.innerWidth, vh = window.innerHeight;
    if (document.documentElement.scrollWidth > vw + 1) out.add(`page scrolls sideways (${document.documentElement.scrollWidth}px wide)`);
    const navs = Array.from(document.querySelectorAll("nav")) as HTMLElement[];
    const clippedByScroller = (el: Element) => {
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        const ox = getComputedStyle(a).overflowX;
        if (ox === "auto" || ox === "scroll" || ox === "hidden" || ox === "clip") return true;
      }
      return false;
    };
    const name = (el: HTMLElement) =>
      ((el.getAttribute("aria-label") || el.textContent || el.getAttribute("placeholder") || el.tagName).trim().replace(/\s+/g, " ").slice(0, 40));
    const describe = (h: Element | null) => h ? `<${h.tagName.toLowerCase()} class="${(h.getAttribute("class") || "").slice(0, 50)}">` : "nothing";
    const total = document.documentElement.scrollHeight;
    for (let y = 0, step = 0; step < 12; y += Math.floor(vh * 0.75), step++) {
      window.scrollTo(0, y);
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const covers = navs.map(n => ({ n, r: n.getBoundingClientRect() })).filter(c => c.r.height && getComputedStyle(c.n).position !== "static");
      const controls = document.querySelectorAll<HTMLElement>("a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=menuitem]");
      for (const el of Array.from(controls)) {
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) continue;                               // hidden or screen-reader only
        // Not something you can see or tap: a closed sheet (inert, opacity 0, pointer-events none)
        if (el.closest("[inert], [aria-hidden='true']") || getComputedStyle(el).pointerEvents === "none"
            || !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        if (cy < 0 || cy > vh || cx < 0 || cx > vw) {
          if (cy >= 0 && cy <= vh && !clippedByScroller(el)) out.add(`${name(el)}: cut off at the screen edge`);
          continue;
        }
        const inNav = covers.find(c => c.n.contains(el));
        if (!inNav && covers.some(c => cy >= c.r.top && cy <= c.r.bottom && cx >= c.r.left && cx <= c.r.right)) continue;  // under a sticky bar while scrolled
        if (!clippedByScroller(el) && (r.right > vw + 1 || r.left < -1)) out.add(`${name(el)}: cut off at the screen edge`);
        const hit = document.elementFromPoint(cx, cy);
        if (!hit || !(hit === el || el.contains(hit) || hit.contains(el))) out.add(`${name(el)}: covered by ${describe(hit)}`);
      }
      if (y + vh >= total) break;
    }
    window.scrollTo(0, 0);
    return [...out];
  });
}

for (const [who, pages] of [[ADMIN, ADMIN_PAGES], [VIEWER, VIEWER_PAGES]] as const) {
  for (const path of pages) {
    test(`layout holds on ${path} for ${who.user}, phone to wide monitor`, async ({ page }, info) => {
      test.skip(info.project.name !== "desktop", "widths are set explicitly");
      test.setTimeout(120_000);
      await signIn(page, who);
      await page.goto(path);
      await page.waitForTimeout(1500);                                          // data, charts and fonts settle
      const found: string[] = [];
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: width < 768 ? 800 : 900 });
        await page.waitForTimeout(350);
        for (const p of await layoutProblems(page)) found.push(`${width}px: ${p}`);
      }
      expect(found).toEqual([]);
    });
  }
}
