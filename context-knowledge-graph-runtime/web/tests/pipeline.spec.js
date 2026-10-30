import { test, expect } from '@playwright/test';

const open = async page => {
  await page.goto('http://127.0.0.1:8080');
  await expect(page.getByText('Atlas connected', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run pipeline' })).toBeEnabled();
};
const run = async page => {
  await expect(page.getByRole('button', { name: 'Run pipeline' })).toBeEnabled();
  await page.getByRole('button', { name: 'Run pipeline' }).click();
  await expect(page.locator('.execution-note')).toContainText('candidate evidence', { timeout: 120000 });
  await expect(page.locator('[role="alert"]')).toHaveCount(0);
};

test('domain-entry evolution discovers all effective seeds and preserves version inspection', async ({ page }) => {
  test.setTimeout(120000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await open(page);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('right rules');
  await run(page);
  await expect(page.locator('.result-heading')).toContainText('5 seed document(s)');
  await page.getByRole('button', { name: 'Stage pipeline', exact: true }).click();
  await expect(page.locator('.code-pane')).toContainText('$graphLookup');
  await expect(page.locator('.code-pane')).toContainText('ISODate(');
  await expect(page.locator('.code-pane')).toContainText('entryPoint');
  await expect(page.locator('.code-pane')).not.toContainText('ObjectId(');
  await page.getByRole('button', { name: 'Relationships', exact: true }).click();
  await expect(page.getByRole('img', { name: 'Retrieved rule relationship graph' })).toBeVisible();
  expect(await page.locator('.stage-content .graph-node').count()).toBeGreaterThan(18);
  const expandedCount = await page.locator('.stage-content .graph-node').count();
  await page.getByRole('button', { name: /Versioned rule relationships/ }).click();
  await expect(page.locator('.relationship-history')).toContainText('Version 2');
  await expect(page.locator('.relationship-history')).toContainText('Version 3');
  await page.screenshot({path:'../data/pipeline-workbench-known.png',fullPage:true});
  await page.getByLabel('Maximum graph depth').focus();
  await page.getByLabel('Maximum graph depth').press('Home');
  await page.getByLabel('Maximum graph depth').press('ArrowRight');
  await page.getByLabel('Maximum graph depth').press('ArrowRight');
  await expect(page.getByLabel('Maximum graph depth')).toHaveValue('2');
  await run(page);
  await expect(page.locator('.result-heading')).toContainText('5 seed document(s)');
  await page.getByRole('button', { name: 'Relationships', exact: true }).click();
  expect(await page.locator('.stage-content .graph-node').count()).toBeLessThan(expandedCount);
  expect(errors).toEqual([]);
});

test('discovery executes native reranking and exposes query steering for both questions', async ({ page }) => {
  test.setTimeout(240000);
  const events=[];const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('response',async response=>{
    if(response.url().endsWith('/api/explorer/run')){
      try{events.push(...(await response.text()).trim().split('\n').map(JSON.parse));}catch{}
    }
  });
  await open(page);
  await page.getByRole('button', { name: /Discover and traverse/ }).click();
  await page.getByLabel('Demo question').selectOption('oopm');
  await expect(page.getByLabel('Retrieval profile')).toHaveValue('terminology_rrf');
  await run(page);
  await expect(page.locator('.result-row')).toHaveCount(3);
  await expect(page.locator('.stage-step').filter({hasText:'$rerank'})).toContainText('3 documents');
  await page.getByRole('button', { name: 'Query context', exact: true }).click();
  await expect(page.locator('.context-pane')).toContainText('out-of-pocket maximum');
  await expect(page.locator('.context-pane')).toContainText('$90.00');
  await expect(page.locator('.context-pane')).toContainText('$0.00');
  await page.getByRole('button', { name: 'Relationships', exact: true }).click();
  await expect(page.locator('.stage-content .graph-node').first()).toBeVisible();
  await page.screenshot({path:'../data/pipeline-workbench-discovery.png',fullPage:true});
  await page.getByLabel('Demo question').selectOption('charge25');
  await expect(page.getByLabel('Retrieval profile')).toHaveValue('context_rrf');
  await expect(page.getByLabel('Rules effective on')).toHaveValue('2026-09-15');
  await run(page);
  await page.getByRole('button', { name: 'Query context', exact: true }).click();
  await expect(page.locator('.context-pane')).toContainText('demo-claim-prior');
  await expect(page.locator('.context-pane')).toContainText('$25.00');
  await expect.poll(()=>events.filter(e=>e.kind==='stage'&&e.id==='rerank'&&e.status==='completed').length).toBe(2);
  expect(events.filter(e=>e.status==='failed')).toEqual([]);
  expect(errors).toEqual([]);
});

test('memory evolution is a conceptual handoff with no memory execution', async ({page})=>{
  await open(page);
  let runs=0;page.on('request',r=>{if(r.url().endsWith('/api/explorer/run'))runs++;});
  await page.getByRole('button',{name:/Reuse what you know/}).click();
  await expect(page.locator('.memory-panel')).toContainText('no cache or memory lookup runs');
  await expect(page.locator('.memory-flow')).toContainText('Procedural memory');
  await expect(page.getByRole('button',{name:'Run pipeline'})).toHaveCount(0);
  expect(runs).toBe(0);
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('.memory-panel')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.screenshot({path:'../data/pipeline-workbench-mobile.png',fullPage:true});
});

test('pipeline controls fit on a narrow screen', async ({page})=>{
  await page.setViewportSize({width:390,height:844});
  await open(page);
  await expect(page.getByRole('button',{name:'Run pipeline'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.screenshot({path:'../data/pipeline-workbench-mobile-controls.png',fullPage:true});
});


test('isolated rule versions expose distinct content and non-overlapping dates', async ({page})=>{
  await open(page);
  await page.getByRole('button',{name:/Versioned rule content/}).click();
  const version=page.getByLabel('Example rule version');
  await expect(version).toContainText('Version 1');
  await expect(version).toContainText('Version 2');
  await expect(version).toContainText('Version 3');
  await expect(page.locator('.document-view pre')).toContainText('"maxDispensingFee": 150');
  await expect(page.locator('.document-view pre')).toContainText('2026-05-01');
  await version.selectOption({label:'Version 2 · from 2026-05-01'});
  await expect(page.locator('.document-view pre')).toContainText('"maxDispensingFee": 125');
  await expect(page.locator('.document-view pre')).toContainText('2026-09-01');
  await version.selectOption({label:'Version 3 · from 2026-09-01'});
  await expect(page.locator('.document-view pre')).toContainText('"maxDispensingFee": 100');
  await expect(page.locator('.document-view pre')).toContainText('467618533fe0438a98b1dde4');
});


test('relationship versions show linked chains without individual rule payloads', async ({page})=>{
  await open(page);
  await page.getByRole('button',{name:/Versioned rule relationships/}).click();
  const panel=page.getByRole('region',{name:'Versioned rule relationships'});
  await expect(panel.locator('pre')).toHaveCount(0);
  await expect(panel.locator('.graph-node')).toHaveCount(3);
  await expect(panel).toContainText('MAC List Effective Version Selection');
  await expect(panel).toContainText('Drug Product Pricing Identifier Resolution');
  await expect(panel).not.toContainText('ruleData');
  await panel.getByRole('button',{name:/Version 2/}).click();
  await expect(panel.locator('.graph-node')).toHaveCount(1);
  await expect(panel).toContainText('no declared downstream relationships');
  await panel.getByRole('button',{name:/Version 3/}).click();
  await panel.getByRole('button',{name:'Show linked chains'}).click();
  await expect(panel.locator('.graph-node')).toHaveCount(19);
  await page.screenshot({path:'../data/versioned-relationships.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
});


test('capability guide maps business questions to procedures rules and reusable domains', async ({ page }) => {
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await open(page);
  const guide=page.getByRole('region', {name:'Capabilities and data domains'});
  await expect(guide).toContainText('Why is my copay $50 instead of $10 like last time?');
  await expect(guide.locator('.capability-mapping article')).toHaveCount(3);
  await expect(guide.locator('.domain-chips')).toContainText('PA if relevant');
  await guide.getByRole('button', {name:'Investigate OOP maximum',exact:true}).click();
  await expect(guide).toContainText('Check accumulator timing and eligible amounts');
  await expect(guide.locator('.domain-chips span')).toHaveCount(3);
  await guide.getByRole('button', {name:'Explain PA impact',exact:true}).click();
  await expect(guide).toContainText('Separate coverage approval from a cost-sharing exception');
  await guide.getByText('Explore 10 example capabilities and their data domains',{exact:true}).click();
  await expect(guide.locator('tbody tr')).toHaveCount(10);
  await expect(guide).toContainText('not ten implemented agents');
  await guide.scrollIntoViewIfNeeded();
  await page.screenshot({path:'../data/capability-guide-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect(guide).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:'../data/capability-guide-mobile.png',fullPage:true});
  expect(errors).toEqual([]);
});


test('relationship hover and focus highlight only outgoing edges and reset', async ({page})=>{
  await open(page);
  await page.getByRole('button',{name:/Versioned rule relationships/}).click();
  const panel=page.getByRole('region',{name:'Versioned rule relationships'});
  const root=panel.locator('.graph-node').first();
  await root.hover();
  await expect(panel.locator('.graph-edge.highlighted')).toHaveCount(2);
  await expect(panel.locator('.graph-node.connected')).toHaveCount(2);
  await panel.locator('h3').hover();
  await expect(panel.locator('.graph-edge.highlighted')).toHaveCount(0);
  await root.focus();
  await expect(panel.locator('.graph-edge.highlighted')).toHaveCount(2);
  await page.keyboard.press('Tab');
  await expect(panel.locator('.graph-edge.highlighted')).toHaveCount(0);
  await panel.getByRole('button',{name:'Show linked chains'}).click();
  await panel.locator('.graph-node').first().hover();
  await expect(panel.locator('.graph-edge.highlighted')).toHaveCount(2);
  await page.screenshot({path:'../data/relationship-hover.png',fullPage:true});
  await page.goto('http://127.0.0.1:8080/legacy');
  const coordinator=page.locator('.react-flow__node[data-id="coordinator"]');
  await coordinator.hover();
  await expect(page.locator('.react-flow__edge[data-id="route-claim"] path.react-flow__edge-path')).toHaveCSS('stroke-width','4px');
  await page.getByRole('heading',{name:'Context, connected.'}).hover();
  await expect(page.locator('.react-flow__edge[data-id="route-claim"] path.react-flow__edge-path')).not.toHaveCSS('stroke-width','4px');
  await page.route('**/api/investigate/stream', async route=>{
    await route.fulfill({contentType:'application/x-ndjson',body:JSON.stringify({kind:'answer',id:'hover-fixture',agent:'coordinator',status:'completed',answer:'Browser fixture',evidence:[],findings:[{claim_id:'fixture-claim',status:'supported',missing:[],details:{member_paid_cents:2500,plan_ref:'fixture-plan',classification:'standard'}}]})+'\n'});
  });
  await page.getByRole('button',{name:'Investigate claim →'}).click();
  await page.getByRole('button',{name:'Business explanation',exact:true}).click();
  const business=page.locator('.business');
  const question=business.locator('g.node').filter({hasText:'Pricing question'});
  await expect(question).toBeVisible();
  await question.hover();
  await expect(business.locator('.relationship-highlight')).toHaveCount(1);
  await expect(business.locator('.relationship-highlight')).toHaveCSS('stroke-width','4px');
  await business.locator('summary').hover();
  await expect(business.locator('.relationship-highlight')).toHaveCount(0);
  await question.focus();
  await expect(business.locator('.relationship-highlight')).toHaveCount(1);

});

test('full pipeline button compares latency without replacing teaching results', async ({page})=>{
  test.setTimeout(180000);
  const runs=[];
  page.on('response',async response=>{
    if(response.url().endsWith('/api/explorer/run')){
      runs.push({request:response.request().postDataJSON(),events:(await response.text()).trim().split('\n').map(JSON.parse)});
    }
  });
  await open(page);
  await expect(page.getByLabel('Execution mode')).toHaveCount(0);
  await page.getByRole('button',{name:/Discover and traverse/}).click();
  await page.getByLabel('Demo question').selectOption('oopm');
  await run(page);
  await expect.poll(()=>runs.length).toBe(1);
  expect(runs[0].request.execution_mode).toBe('preview');
  expect(runs[0].events.find(e=>e.kind==='complete').aggregationCalls).toBe(3);
  await page.locator('.stage-step').filter({hasText:'Hybrid search'}).click();
  const before=await page.locator('.result-row').allTextContents();
  expect(before.length).toBe(20);
  await page.getByRole('button',{name:'Run full pipeline',exact:true}).click();
  await expect.poll(()=>runs.length).toBe(2);
  await expect(page.getByRole('button',{name:'Run full pipeline',exact:true})).toBeEnabled();
  expect(runs[1].request.execution_mode).toBe('single');
  expect(runs[1].events.find(e=>e.kind==='complete').aggregationCalls).toBe(1);
  expect(await page.locator('.result-row').allTextContents()).toEqual(before);
  await expect(page.locator('.stage-step.completed')).toHaveCount(3);
  const comparison=page.getByRole('region',{name:'Pipeline latency comparison'});
  const previewMs=runs[0].events.filter(e=>e.status==='completed').reduce((sum,e)=>sum+e.elapsedMs,0);
  const fullMs=runs[1].events.find(e=>e.status==='completed').elapsedMs;
  await expect(comparison.locator('strong').nth(0)).toHaveText(`${previewMs} ms`);
  await expect(comparison.locator('strong').nth(1)).toHaveText(`${fullMs} ms`);
  const difference=previewMs-fullMs;
  await expect(comparison.locator('strong').nth(2)).toHaveText(difference===0?'Same time':`${Math.abs(difference)} ms ${difference>0?'less':'more'}`);
  await page.getByLabel('Demo question').selectOption('charge25');
  await page.getByLabel('Vector search mode').selectOption('ann');
  await expect(comparison.locator('strong').nth(0)).toHaveText('—');
  await expect(comparison.locator('strong').nth(1)).toHaveText('—');
  await run(page);
  await page.getByRole('button',{name:'Run full pipeline',exact:true}).click();
  await expect.poll(()=>runs.length).toBe(4);
  await expect(page.getByRole('button',{name:'Run full pipeline',exact:true})).toBeEnabled();
  expect(runs[3].events.find(e=>e.kind==='plan').plan.queryConfig.vectorMode).toBe('ann');
  expect(runs[3].events.find(e=>e.kind==='complete').aggregationCalls).toBe(1);
  await page.screenshot({path:'../data/full-pipeline-latency-comparison.png',fullPage:true});
  await page.route('**/api/explorer/run',async route=>{
    await route.fulfill({contentType:'application/x-ndjson',body:JSON.stringify({kind:'stage',id:'graph',status:'failed',message:'Browser fixture full-run failure'})+'\n'});
  });
  const retained=await page.locator('.result-row').allTextContents();
  await page.getByRole('button',{name:'Run full pipeline',exact:true}).click();
  await expect(comparison.getByRole('alert')).toContainText('Browser fixture full-run failure');
  expect(await page.locator('.result-row').allTextContents()).toEqual(retained);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('query context is discovery-only and explains each profile using actual signals',async ({page})=>{
  await open(page);
  await expect(page.getByRole('button',{name:'Query context',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:/Discover and traverse/}).click();
  await page.getByRole('button',{name:'Query context',exact:true}).click();
  await page.getByLabel('Retrieval profile').selectOption('balanced_rrf');
  await expect(page.locator('.query-boosts')).toContainText('No extra lexical boosts');
  await expect(page.locator('.profile-comparison .selected-profile')).toContainText('Balanced RRF');
  await page.getByLabel('Demo question').selectOption('oopm');
  await expect(page.locator('.query-terms')).toContainText('out-of-pocket maximum');
  await expect(page.locator('.query-terms')).toContainText('family out-of-pocket accumulator');
  await expect(page.locator('.query-boosts')).toContainText('4×');
  await expect(page.locator('.query-boosts')).toContainText('3×');
  await expect(page.locator('.fusion-note')).toContainText('1:1');
  await page.screenshot({path:'../data/query-context-profile.png',fullPage:true});
  await page.getByLabel('Demo question').selectOption('charge25');
  await expect(page.locator('.query-terms')).toContainText('Recorded context added');
  await expect(page.locator('.query-boosts')).toContainText('copay');
  await expect(page.locator('.profile-comparison .selected-profile')).toContainText('Claim context + RRF');
  await page.getByRole('button',{name:/Domain entry points/}).click();
  await expect(page.getByRole('button',{name:'Query context',exact:true})).toHaveCount(0);
  await expect(page.locator('.context-pane')).toHaveCount(0);
});
