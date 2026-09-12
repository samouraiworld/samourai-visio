import { defineConfig, devices } from '@playwright/test'

const artifacts = process.env.E2E_ARTIFACTS_DIR ?? '../../artifacts/e2e'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 30_000 },
  forbidOnly: true,
  reporter: [
    ['list'],
    ['html', { outputFolder: `${artifacts}/playwright-report`, open: 'never' }],
    ['junit', { outputFile: `${artifacts}/results.xml` }],
  ],
  outputDir: `${artifacts}/test-results`,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:3000',
    locale: 'en-GB',
    viewport: { width: 1440, height: 1000 },
    permissions: ['camera', 'microphone'],
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      args: [
        '--use-fake-device-for-media-stream',
        '--use-fake-ui-for-media-stream',
        '--autoplay-policy=no-user-gesture-required',
      ],
    },
  },
  webServer: {
    command:
      '/frontend/node_modules/.bin/vite preview --config /e2e/vite.config.mjs --host 0.0.0.0 --port 3000 --strictPort',
    url: 'http://localhost:3000',
    timeout: 30_000,
    reuseExistingServer: false,
  },
})
