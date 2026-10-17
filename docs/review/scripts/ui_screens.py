"""Phase 6: screenshot every screen at 375/768/1440 px and run axe-core (WCAG 2.2 AA) on each.

Runs against the LOCAL demo stack only (UI on 127.0.0.1:3001 → API on :8000 with a SQLite demo DB).
Uses the installed Microsoft Edge through Playwright (no browser download) and axe-core from a
scratch npm folder. Session tokens are read from a scratch file and never printed.

    <review-venv>/python -I docs/review/scripts/ui_screens.py <tokens.json> <axe.min.js>
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "review" / "screenshots"
BASE = "http://127.0.0.1:3001"
WIDTHS = {375: 812, 768: 1024, 1440: 900}

ADMIN_PAGES = [("research", "/"), ("signals", "/signals"), ("signal-detail", "/signals/NF-261016-001"),
               ("paper", "/paper"), ("performance", "/performance"), ("agents", "/agents"),
               ("history", "/history"), ("usage", "/usage"), ("connectors", "/connectors"),
               ("account", "/account"), ("not-found", "/does-not-exist")]
VIEWER_PAGES = [("viewer-signals", "/signals"), ("viewer-admins-only", "/agents")]
ANON_PAGES = [("sign-in", "/signals")]

PROBE = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                     return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const coarse = matchMedia('(pointer: coarse)').matches;
  const small = Array.from(document.querySelectorAll('button, select, [role=tab], a[href]'))
    .filter(e => vis(e) && !(e.tagName === 'A' && e.closest('p, td, li span, dd')))
    .filter(e => { const r = e.getBoundingClientRect(); return r.height < 24 || r.width < 24; }).length;
  const smallTouch = coarse ? Array.from(document.querySelectorAll('button, select, [role=tab]'))
    .filter(e => vis(e) && e.getBoundingClientRect().height < 40).length : null;
  return { innerWidth, scrollWidth: document.documentElement.scrollWidth,
           h1: document.querySelector('h1')?.innerText ?? null, under24px: small, touchUnder40px: smallTouch };
}"""

CLS = """() => new Promise(res => { let v = 0; try { new PerformanceObserver(l => l.getEntries()
  .forEach(e => { if (!e.hadRecentInput) v += e.value; })).observe({ type: 'layout-shift', buffered: true }); } catch (e) {}
  setTimeout(() => res(Math.round(v * 10000) / 10000), 300); })"""

AXE = """async () => { const r = await axe.run(document, { runOnly: { type: 'tag', values:
  ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } });
  return r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
                                  sample: v.nodes.slice(0, 2).map(n => n.target.join(' ')) })); }"""


def visit(browser, token: str | None, slug: str, path: str, axe_js: str, extra=None) -> dict:
    result = {"screen": slug, "path": path, "widths": {}}
    for width, height in WIDTHS.items():
        touch = width < 1024
        ctx = browser.new_context(viewport={"width": width, "height": height}, has_touch=touch, is_mobile=width < 768,
                                  device_scale_factor=1)
        ctx.add_init_script("(t => { try { if (t) localStorage.setItem('auth.session', t); else localStorage.clear(); } catch (e) {} })"
                            f"({json.dumps(token)})")
        page = ctx.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text[:160]) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {str(e)[:160]}"))
        page.goto(BASE + path, wait_until="networkidle")
        page.wait_for_timeout(1500)
        if extra:
            extra(page, width)
            page.wait_for_timeout(600)
        probe = page.evaluate(PROBE)
        cls = page.evaluate(CLS)
        page.screenshot(path=str(OUT / f"{slug}-{width}.png"), full_page=True)
        entry = {**probe, "cls": cls, "console_errors": [e for e in errors if "favicon" not in e][:6]}
        if width in (375, 1440):
            page.add_script_tag(content=axe_js)
            entry["axe"] = page.evaluate(AXE)
        result["widths"][width] = entry
        ctx.close()
    return result


def open_more_sheet(page, width):
    if width < 1024:
        page.click("button[aria-controls=more-sheet]")


def main() -> None:
    tokens = json.loads(Path(sys.argv[1]).read_text())
    axe_js = Path(sys.argv[2]).read_text(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for slug, path in ADMIN_PAGES:
            report.append(visit(browser, tokens["admin"], slug, path, axe_js))
        report.append(visit(browser, tokens["admin"], "more-sheet", "/signals", axe_js, open_more_sheet))
        for slug, path in VIEWER_PAGES:
            report.append(visit(browser, tokens["viewer"], slug, path, axe_js))
        for slug, path in ANON_PAGES:
            report.append(visit(browser, None, slug, path, axe_js))
        browser.close()
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
