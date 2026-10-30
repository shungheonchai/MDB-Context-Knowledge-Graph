import { test, expect } from '@playwright/test';
test('live Atlas/Grove investigation exposes context lineage and Mermaid explanation', async ({ page }) => {
  test.setTimeout(180000);
  const errors = [];
  let executionEvents = [];
  page.on('response', async response => {
    if (response.url().endsWith('/api/investigate/stream')) {
      try { executionEvents = (await response.text()).trim().split('\n').map(JSON.parse); } catch {}
    }
  });
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:8080/legacy');
  await expect(page.getByText('Atlas connected')).toBeVisible();
  await page.getByLabel('Choose prescription scenario').selectOption('P08');
  await expect(page.getByLabel('Ask a pricing question')).not.toHaveValue(/demo-claim|Cite exact source records/);
  await page.getByRole('button', { name: 'Investigate claim →' }).click();
  await expect(page.locator('.answer')).toContainText('reconstructed', { timeout: 160000 });
  await expect(page.getByRole('button', { name: 'Investigate claim →' })).toBeEnabled();
  await page.locator('.react-flow__node[data-id="ctx-claim"]').click();
  await expect(page.locator('.inspector')).toContainText('claims/demo-claim-missing-all-refs');
  await page.screenshot({ path: '../data/context-explorer-live.png', fullPage: true });
  await page.getByRole('button', { name: 'Relationships', exact: false }).first().click();
  await expect(page.locator('.react-flow__edge').first()).toBeAttached();
  await page.getByRole('button', { name: 'Business explanation', exact: true }).click();
  await expect(page.locator('.business svg')).toBeVisible();
  await page.screenshot({ path: '../data/context-explorer-business.png', fullPage: true });
  const modelEvents = executionEvents.filter(e => e.kind === 'model');
  expect(modelEvents.some(e => e.status === 'completed')).toBeTruthy();
  expect(modelEvents.filter(e => e.status === 'failed')).toEqual([]);
  expect(executionEvents.some(e => e.kind === 'context_write' && e.status === 'completed')).toBeTruthy();
  expect(errors).toEqual([]);
});

test('opens connected without a token or manual connection', async ({ page }) => {
  await page.goto('http://127.0.0.1:8080/legacy');
  await expect(page.getByText('Atlas connected')).toBeVisible();
  await expect(page.getByLabel('Demo access token')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Connect', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Investigate claim →' })).toBeEnabled();
  await expect(page.getByRole('combobox')).toContainText('Same medicine, higher copay');
});

test('scenario questions are human-facing and submit background references', async ({ page }) => {
  await page.goto('http://127.0.0.1:8080/legacy');
  await expect(page.getByText('Atlas connected')).toBeVisible();
  await expect(page.getByLabel('Ask a pricing question')).toHaveValue('Why is my copay $75 this time when I only paid $25 for the same medicine last time?');
  await page.getByLabel('Choose prescription scenario').selectOption('P04');
  await expect(page.getByLabel('Ask a pricing question')).toHaveValue('My prior authorization was approved. Why do I still have to pay $75?');
  let payload;
  await page.route('**/api/investigate/stream', async route => {
    payload = route.request().postDataJSON();
    await route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({kind:'run',agent:'coordinator',status:'completed',sequence:1,id:'browser-only-check'})+'\n' });
  });
  await page.getByRole('button', { name: 'Investigate claim →' }).click();
  await expect.poll(() => payload?.scenario_id).toBe('P04');
  expect(payload.question).toBe('My prior authorization was approved. Why do I still have to pay $75?');
  expect(payload.question).not.toContain('demo-claim');
});
