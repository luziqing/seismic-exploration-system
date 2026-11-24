const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const base = process.env.SAM3_URL || 'http://127.0.0.1:9340';
const noisy = 'synthetic_deep_v1';
const clean = noisy + '_clean';

async function main() {
    const browser = await chromium.launchPersistentContext(process.env.E4_PROFILE, {
        channel: 'chrome', headless: true, viewport: { width: 1600, height: 900 },
        acceptDownloads: true, downloadsPath: process.env.E4_DOWNLOADS,
        args: ['--disable-gpu', '--disable-crash-reporter'],
    });
    try {
        const page = await browser.newPage();
        const errors = [];
        const requests = [];
        const downloads = [];
        const runIds = new Set();
        page.on('pageerror', error => errors.push(error.message));
        page.on('console', message => {
            if (message.type() !== 'error') return;
            if (message.location().url.endsWith('/favicon.ico') && message.text().includes('404')) return;
            errors.push(message.text());
        });
        page.on('request', request => requests.push(new URL(request.url()).pathname));
        page.on('download', download => downloads.push(download));
        await page.goto(base);
        const origin = await page.evaluate(() => performance.timeOrigin);
        await page.waitForFunction(() => volInfo.name === 'synthetic_deep_v1' && currentSliceData);
        await page.fill('#lineNo', '23');
        await page.click('#btnGoLine');
        await page.waitForFunction(() => curIndex === 23 && currentSliceData);

        for (let cycle = 1; cycle <= 3; cycle++) {
            await page.selectOption('#compareSelect', 'off');
            if (cycle > 1) {
                await page.click('#btnNoisePair');
                await page.waitForFunction(() => volInfo.name === 'synthetic_deep_v1' && currentSliceData);
            }
            await page.click('#btnModeRaw');
            await page.waitForFunction(() => sliceMode === 'raw' && currentSliceData);
            await page.click('#btnModeLow');
            await page.waitForFunction(() => sliceMode === 'lowfreq' && currentSliceData);
            await showCompare(page, 'lowfreq', noisy, 'raw');
            await showCompare(page, 'noise', clean, 'lowfreq');
            await page.click('#btnNoisePair');
            await page.waitForFunction(() => volInfo.name === 'synthetic_deep_v1_clean' && curIndex === 23 && currentSliceData);
            await page.click('#btnClearMask');
            await page.click('#btnInclude');
            assert(await page.isChecked('#autoRefine'));
            const box = await page.locator('#seismicCanvas').boundingBox();
            // Center of the synthetic truth prompt used by test_refine_e2e.py for this slice.
            await page.mouse.click(box.x + box.width * (14.5 / 48), box.y + box.height * (225.5 / 256));

            if (cycle === 1) {
                for (const volume of [noisy, clean]) {
                    assert(requests.includes('/api/npy/' + volume + '/masks'));
                    assert(!requests.some(path => path.startsWith('/api/npy/' + volume + '/mask/sam_mask/')));
                }
            }
            const [response, footprint] = await Promise.all([
                page.waitForResponse(r => r.url().endsWith('/' + clean + '/refine'), { timeout: 90000 }),
                page.waitForResponse(r => r.url().endsWith('/' + clean + '/mask/sam_mask/footprint'), { timeout: 90000 }),
                page.click('#btnRunSAM'),
            ]);
            assert(response.ok());
            assert(footprint.ok());
            assert.equal(response.request().postDataJSON().mode, 'raw');
            const run = await response.json();
            assert(!runIds.has(run.run_id));
            runIds.add(run.run_id);
            assert(run.rounds.length >= 2);
            const selected = run.best_round === 1 ? 2 : 1;
            await page.locator('tr[data-round="' + selected + '"]').click();
            await page.waitForFunction(round => refineSelected === round, selected);
            await page.screenshot({ path: 'data/e4-' + cycle + '.png' });

            await page.click('#btnExportMask');
            for (let attempt = 0; attempt < 100 && downloads.length < cycle * 3; attempt++) {
                await page.waitForTimeout(100);
            }
            const batch = downloads.slice((cycle - 1) * 3, cycle * 3);
            assert.deepEqual(batch.map(download => download.suggestedFilename().split('.').pop()).sort(), ['csv', 'geojson', 'json']);
            for (const download of batch) {
                const contents = fs.readFileSync(await download.path(), 'utf8');
                assert(contents.length);
                if (download.suggestedFilename().endsWith('.geojson')) {
                    const geojson = JSON.parse(contents);
                    assert(geojson.features.length);
                    assert.equal(geojson.properties.round, selected);
                    assert.equal(geojson.properties.run_id, run.run_id);
                }
            }
            assert.equal(await page.evaluate(() => performance.timeOrigin), origin);
            console.log('PASS cycle ' + cycle + ': run ' + run.run_id + ', selected round ' + selected + ', GeoJSON + CSV + QC log');
        }
        assert.deepEqual(errors, []);
        console.log('PASS 3 cycles on one page; 0 page/console errors (favicon 404 allowed)');
    } finally {
        await browser.close();
    }
}

async function showCompare(page, option, volume, mode) {
    const query = mode === 'raw' ? '' : '?mode=' + mode;
    const [response] = await Promise.all([
        page.waitForResponse(r => r.url().endsWith('/' + volume + '/slice/inline/23' + query)),
        page.selectOption('#compareSelect', option),
    ]);
    assert(response.ok());
    await page.locator('#compareCanvas').waitFor();
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
