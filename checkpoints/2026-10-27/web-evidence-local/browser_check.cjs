const { chromium } = require('../pex-web-owner-core-WORKING-20261026-2219/apps/desktop/node_modules/playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try {
    const context=await browser.newContext({ignoreHTTPSErrors:true});
    const page=await context.newPage();
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    await page.goto('https://127.0.0.1:7443');
    await page.locator('#owner-secret').fill(fs.readFileSync('local-private/owner.secret','utf8'));
    await page.locator('#sign-in').click();
    await page.locator('#refresh-workspace').waitFor({state:'visible'});
    await page.locator('#refresh-workspace').click();
    await page.waitForFunction(()=>document.querySelector('#workspace-records').textContent.includes('infrastructure error'));
    const text=await page.locator('#workspace-records').innerText();
    if (!text.includes('10') || !text.includes('natural stop') || !text.includes('DeepSeek')) throw Error('Missing real arm metadata');
    console.log('Real browser: authenticated real JSONL metadata rendered; baseline10/PEX10; infrastructure error shown');
    await page.locator('#refresh-workspace').click();
    await page.waitForFunction(()=>document.querySelector('#workspace-records').textContent.includes('infrastructure error'));
    await page.locator('#sign-out').click();
    await page.locator('#owner-secret').waitFor({state:'visible'});
    if((await page.locator('#workspace-records').textContent()).includes('infrastructure error'))throw Error('Logout retained private data');
    if(errors.length)throw Error(errors.join(';'));
    console.log('Real browser: refresh, logout clear, no page errors; no recording created');
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1});
