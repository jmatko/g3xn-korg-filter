// Quick WebMIDI probe: does the browser see any MIDI inputs (the G3Xn "ZOOM G")?
// Run: node webmidi_probe.mjs
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      // Try to enable MIDI in headless Chromium
      '--enable-features=WebMidi',
    ],
  });
  const page = await browser.newPage();
  page.on('console', m => console.log('[page]', m.text()));
  page.on('pageerror', e => console.log('[pageerror]', e.message));

  // Minimal page that requests MIDI access and dumps ports.
  await page.setContent(`
    <html><body><pre id="out">starting…</pre>
    <script>
      (async () => {
        const out = document.getElementById('out');
        try {
          if (!navigator.requestMIDIAccess) {
            out.textContent = 'NO navigator.requestMIDIAccess (WebMIDI unsupported)';
            return;
          }
          const access = await navigator.requestMIDIAccess({ sysex: true, sysexAccess: true });
          const ins = [...access.inputs.values()];
          const outs = [...access.outputs.values()];
          out.textContent =
            'inputs: ' + ins.length + '\\n' +
            ins.map(i => '  IN  id=' + i.id + ' name=' + JSON.stringify(i.name) + ' manufacturer=' + i.manufacturer + ' sysex=' + i.sysex).join('\\n') +
            '\\noutputs: ' + outs.length + '\\n' +
            outs.map(o => '  OUT id=' + o.id + ' name=' + JSON.stringify(o.name) + ' manufacturer=' + o.manufacturer).join('\\n');
        } catch (e) {
          out.textContent = 'ERROR: ' + e.name + ': ' + e.message;
        }
      })();
    </script>
    </body></html>
  `);

  await page.waitForTimeout(1500);
  const text = await page.$eval('#out', el => el.textContent);
  console.log('=== WebMIDI probe result ===');
  console.log(text);
  await browser.close();
})().catch(e => { console.error('probe failed:', e); process.exit(1); });