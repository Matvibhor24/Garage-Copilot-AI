import { defineConfig, devices } from '@playwright/test'

// Runs the three screens in demo mode (no backend needed), on a phone and on a laptop. `npm run e2e`
// customer-real.spec.js runs the customer page in normal mode against stubbed real-backend responses.
export default defineConfig({
  testDir: 'e2e',
  timeout: 120_000,
  workers: 1, // two software-WebGL pages at once starve each other
  expect: { timeout: 15_000 }, // software WebGL (no GPU in CI) makes the 3D view slow on a big canvas
  use: { baseURL: 'http://localhost:5180', trace: 'retain-on-failure' },
  projects: [
    { name: 'phone', use: { ...devices['Pixel 7'] } },
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    { command: 'npx vite --mode demo --port 5180 --strictPort', url: 'http://localhost:5180', reuseExistingServer: true },
    // Normal (non-demo) mode for specs that stub the real backend's responses (e2e/customer-real.spec.js)
    { command: 'npx vite --port 5182 --strictPort', url: 'http://localhost:5182', reuseExistingServer: true },
  ],
})
