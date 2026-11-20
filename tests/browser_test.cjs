// npm install --no-save playwright-core; set CHROME_PATH if needed.
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH,
    headless: true, args: ['--disable-gpu'],
  });
  try {
    const page = await browser.newPage({viewport: {width: 1400, height: 1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.recalculate_prompts_txt2img = () => {};
      window.recalculate_prompts_img2img = () => {};
    });
    await page.goto('http://127.0.0.1:7863');
    const shift = page.locator('#txt2img_distilled_cfg_scale input[type=number]');
    const hires = page.locator('#txt2img_hr_distilled_cfg input[type=number]');
    const i2i = page.locator('#img2img_distilled_cfg_scale input[type=number]');
    const preset = page.locator('#forge_ui_preset input');
    const meta = page.locator('#png_metadata textarea');
    async function waitValue(locator, value) {
      await page.waitForFunction(({selector, value}) =>
        Number(document.querySelector(selector)?.value) === value,
        {selector: await locator.evaluate(el => `#${el.closest('[id]').id} input[type=number]`), value});
    }
    async function verify(value, label, target = shift) {
      await waitValue(target, value);
      // Allow dependent preset .change events to finish; immediate values alone
      // would miss the old regression that overwrote metadata after a paste.
      await page.waitForTimeout(1200);
      assert.equal(Number(await target.inputValue()), value, label);
      console.log('PASS', label, value);
    }
    async function choosePreset(value) {
      await preset.click();
      await page.getByRole('option', {name: value, exact: true}).click();
    }
    await verify(1.15, 'initial default');
    for (const value of [0, .65, 1.39, 4.02]) {
      await choosePreset('flux');
      await page.waitForTimeout(400);
      await page.locator('#png_source input[type=file]').setInputFiles(
        path.join(process.env.KREA_SHIFT_TEST_ARTIFACTS, `shift-${value}.png`));
      await page.waitForFunction(value => document.querySelector('#png_metadata textarea')?.value.includes(`Shift: ${value},`), value);
      await page.locator('#png_send').click();
      await verify(value, 'PNG Info from flux preset');
      assert.equal(Number(await hires.inputValue()), .9);
      assert.equal(await preset.inputValue(), 'krea');
      await page.locator('#png_send_i2i').click();
      await verify(value, 'PNG Info to img2img', i2i);
    }
    for (const value of [.65, 0, 4.02]) {
      await choosePreset('flux');
      await page.waitForTimeout(400);
      const file = path.join(process.env.KREA_SHIFT_TEST_ARTIFACTS, `shift-${value}.png`);
      await page.locator('#iib_path textarea').fill(file);
      await page.locator('#iib_choose').click();
      await page.waitForFunction(file => document.querySelector('#iib_ready textarea')?.value === file, file);
      await page.locator('#iib_hidden_img_update_trigger').click();
      await page.waitForFunction(value => document.querySelector('#iib_hidden_img_file_info textarea')?.value.includes(`Shift: ${value},`), value);
      await page.locator('#iib_hidden_tab_txt2img').click();
      await verify(value, 'stock IIB PNG reader + Send to txt2img');
      assert.equal(Number(await hires.inputValue()), .9);
      await page.locator('#iib_hidden_tab_img2img').click();
      await verify(value, 'stock IIB Send to img2img', i2i);
    }
    // Same-preset sends must work too, not just a change from another model.
    await meta.fill('Test scene\nSteps: 8, CFG scale: 1, Seed: 42, UI preset: krea, Version: neo-2.32, Shift: 0.65');
    await page.locator('#png_send').click();
    await verify(.65, 'same-preset PNG send');
    await meta.fill('Test scene\nSteps: 8, CFG scale: 1, Seed: 42, UI preset: krea, Version: neo-2.32');
    await page.locator('#png_send').click();
    await verify(1.15, 'old native Krea PNG fallback');
    await choosePreset('flux');
    await page.waitForTimeout(400);
    await choosePreset('krea');
    await verify(1.15, 'deliberate preset selection still loads defaults');
    assert.equal(await shift.getAttribute('step'), '0.01');
    assert.equal(await shift.getAttribute('min'), '0');
    await page.screenshot({path: path.join(process.env.KREA_SHIFT_TEST_ARTIFACTS, 'browser-pass.png')});
    assert.deepEqual(errors, []);
    console.log('All browser checks passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
