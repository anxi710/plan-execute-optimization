import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'

const localChrome = '/opt/google/chrome/chrome'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 1000 },
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH ?? (existsSync(localChrome) ? localChrome : undefined),
    },
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
