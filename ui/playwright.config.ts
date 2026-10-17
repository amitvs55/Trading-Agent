import { randomBytes } from "node:crypto";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * Browser end-to-end tests (roadmap R-30): the real API on a throwaway SQLite database and a
 * production build of the UI, driven through the core flows with an accessibility gate.
 *
 *   npx playwright test            (locally uses the installed Microsoft Edge: no browser download)
 */

// Fresh test passwords for every run. Set once in the main process; workers inherit the environment.
process.env.E2E_ADMIN_PW ||= `adm-${randomBytes(12).toString("hex")}`;
process.env.E2E_VIEWER_PW ||= `vwr-${randomBytes(12).toString("hex")}`;

const ROOT = path.resolve(__dirname, "..");
const DB = path.join(__dirname, "e2e", ".data", "e2e.db");
const PYTHON = process.env.E2E_PYTHON ?? (process.platform === "win32" ? path.join(ROOT, ".venv", "Scripts", "python.exe") : "python");
const API_PORT = 8100;
const UI_PORT = 3100;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${UI_PORT}`,
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    channel: process.env.CI ? undefined : "msedge",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"], channel: process.env.CI ? undefined : "msedge" } },
  ],
  webServer: [
    {
      command: `"${PYTHON}" ui/e2e/seed.py "${DB}" ${process.env.E2E_ADMIN_PW} ${process.env.E2E_VIEWER_PW} && "${PYTHON}" -m uvicorn api.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: ROOT,
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: { DATABASE_URL: `sqlite:///${DB.replace(/\\/g, "/")}`, WATCHDOG: "off", SECRET_KEY: "e2e-only",
             RESEARCH_IMPORT_LEGACY: "off", PYTHONIOENCODING: "utf-8" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run build && npx next start -p ${UI_PORT}`,
      url: `http://127.0.0.1:${UI_PORT}`,
      env: { API_BASE_URL: `http://127.0.0.1:${API_PORT}`, NEXT_PUBLIC_API_URL: "", NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
