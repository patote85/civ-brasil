import fs from "node:fs";
import { defineConfig } from "@playwright/test";

const SYSTEM_CHROME = "/usr/bin/google-chrome";
const launchOptions =
  !process.env.CI && fs.existsSync(SYSTEM_CHROME) ? { executablePath: SYSTEM_CHROME } : {};

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    headless: true,
    launchOptions,
  },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 20_000,
  },
  projects: [
    {
      name: "desktop-1280x800",
      use: { viewport: { width: 1280, height: 800 } },
    },
    {
      name: "mobile-375x812",
      use: { viewport: { width: 375, height: 812 } },
    },
  ],
});
