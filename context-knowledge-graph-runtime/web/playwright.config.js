import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', use: { browserName: 'chromium', channel: 'chrome', viewport: { width: 1440, height: 1000 } }, reporter: 'list' });
