// Renders scene.html frames with Playwright and pipes them into ffmpeg.
// Usage: node render.js <scene1|scene2> <out.mp4>
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
(async () => {
  const [scene, out] = process.argv.slice(2);
  const FPS = 30;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  await page.goto('file://' + path.join(__dirname, 'scene.html'));
  await page.evaluate(() => document.fonts.ready);
  const dur = await page.evaluate(s => SCENES[s].dur, scene);
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', '-movflags', '+faststart', out],
    { stdio: ['pipe', 'ignore', 'inherit'] });
  const total = dur * FPS;
  for (let f = 0; f < total; f += 10) {
    const batch = await page.evaluate(([s, f0, n, fps]) => {
      const out = [];
      for (let f = f0; f < f0 + n; f++) { renderAt(s, f / fps); out.push(document.getElementById('c').toDataURL('image/jpeg', 0.95).split(',')[1]); }
      return out;
    }, [scene, f, Math.min(10, total - f), FPS]);
    for (const b64 of batch) ff.stdin.write(Buffer.from(b64, 'base64'));
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
})();
