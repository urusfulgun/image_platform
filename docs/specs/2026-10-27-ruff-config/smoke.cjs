// Throwaway smoke test used for F5 task 11; reference for F17 (pytest + Playwright).
//
// Usage, from the devcontainer (uses the frontend's Playwright install):
//   node smoke.cjs "$(getent hosts nginx-gateway | awk '{print $1}')" creds.json <out-dir>
// creds.json: {"username": "smoke-test", "password": "..."}. Reset the password with the
// Keycloak admin API. Do not use a .local email (R20).
// Uploads stay PENDING until F18 provisions the RustFS webhook.
const fs = require('fs');
const zlib = require('zlib');
const { chromium } = require('/workspaces/image_platform/services/frontend/node_modules/playwright');

const [nginxIp, credsPath, outDir] = process.argv.slice(2);
const creds = JSON.parse(fs.readFileSync(credsPath, 'utf8'));
const APP = 'http://image-platform';

function log(step, detail = '') {
  console.log(`${new Date().toISOString().slice(11, 19)} ${step}${detail ? ': ' + detail : ''}`);
}

// A small 64x64 RGB PNG gradient, built by hand so no image library is needed.
function makePng() {
  const w = 64, h = 64;
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf) => {
    let c = 0xffffffff;
    for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type), data]);
    const c = Buffer.alloc(4); c.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, c]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 2; // 8-bit RGB
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w * 3 + 1)] = 0;
    for (let x = 0; x < w; x++) {
      const o = y * (w * 3 + 1) + 1 + x * 3;
      raw[o] = x * 4; raw[o + 1] = y * 4; raw[o + 2] = 128;
    }
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0)),
  ]);
}

(async () => {
  const browser = await chromium.launch({
    // image-platform -> nginx container, like the host's /etc/hosts entry does for 127.0.0.1.
    args: [`--host-resolver-rules=MAP image-platform ${nginxIp}`],
  });
  const context = await browser.newContext();
  // The SPA calls the BFF's published port directly (image-platform:8000); on the host that
  // is a port mapping, here it is forwarded to the BFF container.
  await context.route('http://image-platform:8000/**', async (route) => {
    const url = route.request().url().replace('http://image-platform:8000', 'http://bff-token-handler:8000');
    const response = await route.fetch({ url, maxRedirects: 0 });
    await route.fulfill({ response });
  });
  const page = await context.newPage();
  let ok = false;
  try {
    // 1. Login
    await page.goto(`${APP}/`);
    log('SPA loaded', await page.title());
    await page.getByRole('link', { name: /sign in/i }).click();
    await page.waitForURL(/\/realms\/image-platform\/protocol\/openid-connect\/auth/, { timeout: 15000 });
    log('Keycloak login page', new URL(page.url()).host);
    await page.fill('#username', creds.username);
    await page.fill('#password', creds.password);
    await page.click('#kc-login');
    await page.waitForURL(`${APP}/**`, { timeout: 15000 });
    log('Back on SPA', page.url());

    const sid = (await context.cookies(APP)).find((c) => c.name === 'sid');
    if (!sid) throw new Error('no sid cookie after login');
    log('sid cookie', `httpOnly=${sid.httpOnly} sameSite=${sid.sameSite} domain=${sid.domain}`);

    const api = (path, init = {}) =>
      page.evaluate(async ([p, i]) => {
        const r = await fetch(p, { credentials: 'include', ...i });
        const text = await r.text();
        let body; try { body = JSON.parse(text); } catch { body = text; }
        return { status: r.status, body };
      }, [path, init]);

    const me = await api('/api/me');
    log('/api/me', `${me.status}`);
    if (me.status !== 200) throw new Error(`/api/me -> ${me.status} ${JSON.stringify(me.body)}`);

    // 2. Project + upload
    const name = `smoke-${Date.now()}`;
    const project = await api('/api/proxy/projects/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    });
    log('create project', `${project.status} ${project.body.id || JSON.stringify(project.body)}`);
    if (project.status !== 201) throw new Error('project creation failed');
    const projectId = project.body.id;

    const png = makePng();
    const presign = await api(`/api/proxy/projects/${projectId}/images/presign`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fileName: 'smoke.png', fileSizeBytes: png.length }),
    });
    log('presign', `${presign.status} image_id=${presign.body.image_id} host=${presign.body.upload_url && new URL(presign.body.upload_url).host}`);
    if (presign.status !== 200 && presign.status !== 201) throw new Error(JSON.stringify(presign.body));

    const put = await page.evaluate(async ([url, bytes]) => {
      const r = await fetch(url, {
        method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' },
        body: new Uint8Array(bytes),
      });
      return r.status;
    }, [presign.body.upload_url, [...png]]);
    log('PUT to S3', `${put}`);
    if (put !== 200) throw new Error(`upload PUT -> ${put}`);

    // 3. Wait for OPTIMIZED
    const deadline = Date.now() + 90000;
    let image;
    while (Date.now() < deadline) {
      const list = await api(`/api/proxy/projects/${projectId}/images/`);
      image = Array.isArray(list.body) && list.body.find((i) => i.id === presign.body.image_id);
      if (image && image.status !== 'PENDING') break;
      await page.waitForTimeout(2000);
    }
    log('image status', image ? image.status : 'not listed');
    await page.goto(`${APP}/upload/${projectId}`);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${outDir}/smoke-upload-page.png`, fullPage: true });
    fs.writeFileSync(`${outDir}/smoke-result.json`, JSON.stringify({ projectId, imageId: presign.body.image_id, image }, null, 2));
    ok = image && image.status === 'OPTIMIZED';
  } catch (e) {
    log('FAILED', e.message);
    await page.screenshot({ path: `${outDir}/smoke-failure.png`, fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
  log(ok ? 'SMOKE PASSED' : 'SMOKE FAILED');
  process.exit(ok ? 0 : 1);
})();
