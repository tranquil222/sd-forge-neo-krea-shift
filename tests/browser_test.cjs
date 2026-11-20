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
    const shift = page.locator('#txt2img_krea_shift_fixed input[type=number]');
    const hires = page.locator('#txt2img_krea_shift_hr_fixed input[type=number]');
    const i2i = page.locator('#img2img_krea_shift_fixed input[type=number]');
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
    const advanced = page.locator('#txt2img_krea_shift_options');
    const enabled = page.locator('#txt2img_krea_shift_options-visible-checkbox');
    const details = page.locator('#txt2img_krea_shift_details');
    await enabled.waitFor({state:'visible'});
    assert.equal(await enabled.isChecked(),false);
    assert.equal(await advanced.getByText('Krea2 Shift',{exact:true}).count(),1);
    await advanced.locator('button').first().click();
    await page.locator('#img2img_krea_shift_options button').first().click();
    await page.waitForFunction(() => !document.querySelector('#txt2img_krea_shift_fixed input').disabled);
    assert.equal(await enabled.isChecked(),true);
    assert.equal(await hires.isVisible(),false, 'Hires controls start collapsed');
    await details.locator('button').first().click();
    assert.equal(await hires.isVisible(),true);
    await details.locator('button').first().click();
    assert.equal(await page.locator('#txt2img_distilled_cfg_scale').isVisible(),false);
    assert.equal(await page.locator('#txt2img_hr_distilled_cfg').isVisible(),false);
    assert.equal(await page.locator('#img2img_distilled_cfg_scale').isVisible(),false);
    assert.equal(await shift.isEnabled(),true);
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
    await verify(1.15, 'plugin value remains independent of preset defaults');
    assert.equal(await shift.getAttribute('step'), '0.01');
    assert.equal(await shift.getAttribute('min'), '0');
    const multiple = page.locator('#txt2img_krea_shift_multiple input[type=checkbox]');
    const changing = page.locator('#txt2img_krea_shift_changing input[type=checkbox]');
    await multiple.check();
    const list = page.locator('#txt2img_krea_shift_values textarea');
    await list.waitFor({state:'visible'});
    assert.equal(await page.locator('#txt2img_krea_shift_values').getByText('Shift values',{exact:true}).count(),1);
    assert.equal(await shift.isEnabled(),false);
    assert.equal(await page.locator('#txt2img_krea_shift_fixed').evaluate(el => getComputedStyle(el).opacity),'0.4');
    assert.match(await list.getAttribute('placeholder'), /comma-separated/);
    await list.fill('0.5, 0.65, 1.15');
    await changing.check();
    const from = page.locator('#txt2img_krea_shift_from input');
    const to = page.locator('#txt2img_krea_shift_to input');
    await from.waitFor({state:'visible'});
    assert.equal(await multiple.isChecked(),true);
    assert.equal(await changing.isChecked(),true);
    assert.equal(await list.isVisible(),true);
    assert.equal(await from.isEnabled(),false);
    assert.equal(await shift.isEnabled(),false);
    assert.equal(await page.locator('#txt2img_krea_shift_values').getByText('Shift from values',{exact:true}).count(),1);
    assert.equal(await page.locator('#txt2img_krea_shift_from').evaluate(el => getComputedStyle(el).opacity),'0.4');
    assert.equal(await page.locator('#txt2img_krea_shift_swap').isEnabled(),false);
    await multiple.uncheck();
    await from.fill('2');
    assert.equal(await shift.isEnabled(),false);
    assert.equal(await page.locator('#txt2img_krea_shift_fixed').evaluate(el => getComputedStyle(el).opacity),'0.4');
    await to.fill('0');
    await page.locator('#txt2img_krea_shift_swap').click();
    await verify(0, 'swap From', from);
    assert.equal(Number(await to.inputValue()),2);
    await page.locator('#txt2img_krea_shift_swap').click();
    await verify(2, 'swap From back', from);
    assert.equal(Number(await to.inputValue()),0);
    assert.equal(await list.isVisible(), false);
    console.log('PASS independent list/ramp checkboxes, fixed field and comma placeholder');
    await page.locator('#png_source input[type=file]').setInputFiles(
      path.join(process.env.KREA_SHIFT_TEST_ARTIFACTS, 'shift-ramp.png'));
    await page.waitForFunction(() => document.querySelector('#png_metadata textarea')?.value.includes('interval-v1'));
    await page.locator('#png_send').click();
    await verify(0, 'ramp PNG Info first shift');
    assert.equal(Number(await from.inputValue()), 0);
    assert.equal(Number(await to.inputValue()), 2);
    assert.equal(await page.locator('#txt2img_krea_shift_curve input').inputValue(), 'Hold then switch');
    const switchPoint = page.locator('#txt2img_krea_shift_switch input[type=number]');
    await switchPoint.waitFor({state:'visible'});
    assert.equal(Number(await switchPoint.inputValue()), 70);
    await page.locator('#png_send_i2i').click();
    await verify(0, 'ramp PNG Info img2img', i2i);
    assert.equal(Number(await page.locator('#img2img_krea_shift_to input').inputValue()), 2);
    // Restore fixed, then let the STOCK IIB reader and bridge restore the ramp.
    await meta.fill('Test scene\nSteps: 8, CFG scale: 1, Seed: 42, UI preset: krea, Version: neo-2.32, Shift: 0.65');
    await page.locator('#png_send').click();
    await verify(.65, 'fixed PNG clears previous ramp');
    assert.equal(await from.isVisible(), false);
    assert.equal(await changing.isChecked(),false);
    assert.equal(await multiple.isChecked(),false);
    assert.equal(await shift.isEnabled(),true);
    assert.equal(await page.locator('#txt2img_krea_shift_fixed').evaluate(el => getComputedStyle(el).opacity),'1');
    await enabled.uncheck();
    await page.waitForFunction(() => document.querySelector('#txt2img_krea_shift_fixed input').disabled);
    const rampFile = path.join(process.env.KREA_SHIFT_TEST_ARTIFACTS, 'shift-ramp.png');
    await page.locator('#iib_path textarea').fill(rampFile);
    await page.locator('#iib_choose').click();
    await page.waitForFunction(file => document.querySelector('#iib_ready textarea')?.value === file, rampFile);
    await page.locator('#iib_hidden_img_update_trigger').click();
    await page.waitForFunction(() => document.querySelector('#iib_hidden_img_file_info textarea')?.value.includes('interval-v1'));
    await page.locator('#iib_hidden_tab_txt2img').click();
    await verify(0, 'stock IIB restores complete ramp');
    assert.equal(await enabled.isChecked(),true);
    await from.waitFor({state:'visible'});
    assert.equal(Number(await to.inputValue()), 2);
    assert.equal(Number(await switchPoint.inputValue()), 70);
    await multiple.check();
    await list.waitFor({state:'visible'});
    await list.fill('0.5, 1, 2');
    assert.equal(await page.locator('#txt2img_krea_shift_values').getByText('Shift from values',{exact:true}).count(),1);
    await advanced.screenshot({path: path.join(process.env.KREA_SHIFT_TEST_ARTIFACTS, 'browser-pass.png')});
    await meta.fill('Test scene\nSteps: 8, CFG scale: 1, Seed: 42, UI preset: krea, Version: neo-2.32, Shift: 1.15, Krea Shift enabled: False, Krea Shift mode: Off');
    await page.locator('#png_send').click();
    await verify(1.15, 'disabled PNG restores off state');
    assert.equal(await enabled.isChecked(),false);
    assert.equal(await shift.isEnabled(),false);
    assert.deepEqual(errors, []);
    console.log('All browser checks passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
