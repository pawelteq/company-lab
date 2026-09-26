const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true });
  const results = [];
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  async function check(name, width) {
    await page.getByRole('heading', { level: 1 }).waitFor();
    const result = await page.evaluate(() => ({
      viewport: innerWidth,
      pageWidth: document.documentElement.scrollWidth,
      tinyText: [...document.querySelectorAll('main *')].filter(el => el.getClientRects().length && el.textContent.trim() && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && !(el instanceof SVGElement) && parseFloat(getComputedStyle(el).fontSize) < 12).map(el => ({ text: el.textContent.slice(0, 70), size: getComputedStyle(el).fontSize })),
      unlabeledFields: [...document.querySelectorAll('input, select')].filter(el => !el.labels.length && !el.getAttribute('aria-label')).length,
    }));
    results.push({ name, ...result });
    assert.ok(result.pageWidth <= width, `${name}: horizontal page overflow ${result.pageWidth}/${width}`);
    assert.deepEqual(result.tinyText, [], `${name}: tiny text`);
    assert.equal(result.unlabeledFields, 0);
    await page.screenshot({ path: `.local/audit-${name}-${width}.png`, fullPage: name !== 'profile' });
  }
  try {
    for (const width of [1440, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 950 });
      await page.goto('http://127.0.0.1:8000', { waitUntil: 'networkidle' });
      await page.getByRole('heading', { name: /Najpierw wybierzmy/ }).waitFor();
      await check('overview', width);
      await page.getByRole('button', { name: /Zobacz kandydatów/ }).click();
      await page.getByRole('button', { name: /Otwórz profil/ }).first().waitFor();
      await check('catalog', width);
      await page.getByRole('button', { name: /Otwórz profil/ }).first().click();
      await page.getByRole('heading', { name: 'Finanse z bieżącego profilu', exact: true }).waitFor();
      await check('profile', width);
      const graph = page.locator('.network-canvas');
      if (await graph.count()) { await graph.scrollIntoViewIfNeeded(); await page.screenshot({path: `.local/audit-graph-${width}.png`}); }
      const chart = page.locator('.financial-chart').first();
      if (await chart.count()) { await chart.scrollIntoViewIfNeeded(); await page.screenshot({path: `.local/audit-chart-${width}.png`}); }
      await page.locator('nav').getByRole('button', { name: 'Badania', exact: true }).click();
      await check('research', width);
    }
    await page.goto('http://127.0.0.1:8000');
    await page.keyboard.press('Tab');
    await assert.equal(await page.locator('.skip-link').evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('main').evaluate(el => el === document.activeElement), true);
    await page.getByRole('button', { name: /Zobacz kandydatów/ }).click();
    // Use the name to exercise the debounced search against the real collection.
    await page.getByRole('textbox', { name: 'Szukaj w profilach' }).fill('Super Krak');
    await page.getByRole('button', { name: 'Super Krak', exact: true }).waitFor();
    await page.getByRole('combobox', { name: 'Sortowanie' }).selectOption('revenue');
    await page.getByRole('button', { name: 'Zmień kierunek sortowania' }).click();
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: /Eksport CSV/ }).click();
    assert.equal((await download).suggestedFilename(), 'company-lab-profile-export.csv');
    await page.getByRole('button', { name: 'Super Krak', exact: true }).click();
    await page.getByRole('heading', { name: 'Super Krak', exact: true, level: 1 }).waitFor();
    assert.deepEqual(errors, []);
    fs.writeFileSync('.local/readability-results.json', JSON.stringify({ results, errors, keyboard: 'passed' }, null, 2));
    console.log(`Passed ${results.length} view/viewport checks, keyboard navigation, search, sorting, export and opening a profile by name.`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
