const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 412, height: 915 },
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
    hasTouch: true,
    isMobile: true,
  });
  const page = await context.newPage();
  const logs = [];
  page.on('console', m => logs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  await page.goto('https://eurusd-levels.pages.dev/', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(3000);
  const dom = await page.evaluate(() => {
    const btn = document.getElementById('install');
    const fallback = document.getElementById('install-steps');
    const man = document.querySelector('link[rel="manifest"]');
    const swReg = !!navigator.serviceWorker && !!navigator.serviceWorker.controller;
    const rect = btn ? btn.getBoundingClientRect() : null;
    return {
      title: document.title,
      installBtnVisible: btn ? getComputedStyle(btn).display !== 'none' : 'no-el',
      installBtnText: btn ? btn.textContent : 'no-el',
      rect: rect ? {x: rect.x, y: rect.y, w: rect.width, h: rect.height} : null,
      fallbackVisible: fallback ? getComputedStyle(fallback).display !== 'none' : 'no-el',
      manifestHref: man ? man.getAttribute('href') : null,
      swController: swReg,
    };
  });
  console.log(JSON.stringify({ dom, logs }, null, 2));
  await page.screenshot({ path: 'visual-test-fixed.png', fullPage: true });
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
