// Renders the transparent overlay frames of one video plan.
// Usage: node render_overlay.js plan.json out_dir
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [planPath, outDir] = process.argv.slice(2);
  const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  page.on('pageerror', e => { console.error('overlay error:', e.message); process.exitCode = 1; });
  await page.goto('file://' + path.join(__dirname, 'overlay.html'));
  await page.evaluate(() => document.fonts.ready);
  // make sure the display fonts are loaded before the first frame
  await page.evaluate(async () => {
    for (const f of ["900 100px 'Inter Display'", "800 100px 'Inter Display'", "700 40px 'Inter'", "800 40px 'Inter'"]) await document.fonts.load(f);
  });
  await page.evaluate(p => window.setPlan(p), plan);
  const n = plan.frames, B = 8;
  for (let f = 0; f < n; f += B) {
    const batch = await page.evaluate(([f0, k]) => {
      const out = [];
      for (let i = f0; i < f0 + k; i++) out.push(window.frameData(i));
      return out;
    }, [f, Math.min(B, n - f)]);
    batch.forEach((b64, i) => fs.writeFileSync(path.join(outDir, String(f + i).padStart(4, '0') + '.png'), Buffer.from(b64, 'base64')));
  }
  await browser.close();
})();
