/* Browser acceptance checks for the current profile-screening UI. */
const path = require('node:path');
const assert = require('node:assert/strict');
let chromium;
try {
  ({ chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright'));
} catch (error) {
  console.error('Browser smoke wymaga Playwrighta. Zainstaluj zależność dev i uruchom ponownie.');
  process.exitCode = 2;
  return;
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('http://127.0.0.1:8000', { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: /Najpierw wybierzmy/ }).waitFor();
    await page.getByText(/Pobrane profile/).waitFor();
    await page.screenshot({ path: path.resolve('.local/ui-overview.png'), fullPage: true });

    await page.getByRole('button', { name: /Zobacz kandydatów/ }).click();
    await page.getByRole('heading', { name: 'Firmy wybrane na podstawie opisu', exact: true }).waitFor();
    await page.getByRole('combobox', { name: 'Sortowanie' }).selectOption('revenue');
    await page.getByRole('button', { name: 'Zmień kierunek sortowania' }).click();
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: /Eksport CSV/ }).click();
    assert.equal((await download).suggestedFilename(), 'company-lab-profile-export.csv');
    await page.screenshot({ path: path.resolve('.local/ui-catalog.png'), fullPage: true });

    await page.getByRole('button', { name: /Otwórz profil/ }).first().click();
    await page.getByRole('heading', { name: 'Finanse z bieżącego profilu', exact: true }).waitFor();
    await page.getByText('KOMPLETNOŚĆ DANYCH', { exact: true }).waitFor();
    await page.getByText('Obliczenia dodatkowe', { exact: true }).waitFor();
    await page.getByRole('img', { name: /Mapa powiązań firmy/ }).waitFor();
    await page.screenshot({ path: path.resolve('.local/ui-profile.png'), fullPage: true });

    await page.locator('nav').getByRole('button', { name: 'Badania', exact: true }).click();
    await page.getByRole('heading', { name: 'Przygotuj próbę do analizy', exact: true }).waitFor();
    await page.screenshot({ path: path.resolve('.local/ui-research.png'), fullPage: true });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('nav').getByRole('button', { name: 'Dashboard', exact: true }).click();
    await page.getByRole('heading', { name: /Najpierw wybierzmy/ }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    assert.deepEqual(errors, []);
    console.log('UI passed: current screening, sorting, CSV export, profile completeness, research readiness and mobile width.');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
