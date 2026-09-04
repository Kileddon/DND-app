import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const e2ePort = process.env.TTC_E2E_PORT ?? "8765";
const externalServer = process.env.TTC_E2E_EXTERNAL_SERVER === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${e2ePort}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: externalServer
    ? undefined
    : {
        command: `${resolve("..", ".venv", "Scripts", "python.exe")} -m tabletop_companion.main`,
        cwd: resolve(".."),
        env: {
          TTC_DATABASE_URL: `sqlite:///runtime/playwright-${e2ePort}.sqlite3`,
          TTC_HOST: "127.0.0.1",
          TTC_PORT: e2ePort,
          TTC_LOG_LEVEL: "WARNING",
        },
        url: `http://127.0.0.1:${e2ePort}/health`,
        reuseExistingServer: false,
        timeout: 60_000,
      },
});
