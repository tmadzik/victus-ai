/**
 * Assembles the Next.js standalone output into a self-contained cPanel
 * deployment bundle. Run via `pnpm build:cpanel` (chains after `next build`).
 *
 * Produces:
 *   .next/standalone/                    runnable in place (`pnpm start`)
 *   dist-cpanel/victus-web-cpanel.zip    upload to cPanel
 *
 * Bundle layout (zip root = Passenger application root):
 *   app.js                  Passenger startup file
 *   apps/web/server.js      Next standalone server (used by app.js)
 *   apps/web/.next/...       compiled app + static assets
 *   apps/web/public/...      public assets
 *   node_modules/...        traced production dependencies (incl. workspace
 *                           packages @victus/contracts, @victus/ui)
 *
 * Build-time vs runtime env:
 *   - NEXT_PUBLIC_* values (e.g. NEXT_PUBLIC_API_BASE_URL) are inlined at build
 *     time — set them BEFORE running `build:cpanel`.
 *   - Server-only secrets (AUTH_SECRET, AUTH_URL, INTERNAL_API_BASE_URL,
 *     INTERNAL_SERVICE_TOKEN) are read at runtime — set them in the cPanel
 *     Node.js app screen, not at build time.
 */

import { execFileSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const appDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const standaloneDir = path.join(appDir, '.next', 'standalone');
const appInStandalone = path.join(standaloneDir, 'apps', 'web');
const distDir = path.join(appDir, 'dist-cpanel');
const zipPath = path.join(distDir, 'victus-web-cpanel.zip');

if (!existsSync(path.join(appInStandalone, 'server.js'))) {
  console.error(
    'No standalone output found — run `next build` first (or use `pnpm build:cpanel`).',
  );
  process.exit(1);
}

// Static assets are not traced into standalone — copy them in.
cpSync(path.join(appDir, '.next', 'static'), path.join(appInStandalone, '.next', 'static'), {
  recursive: true,
});
cpSync(path.join(appDir, 'public'), path.join(appInStandalone, 'public'), { recursive: true });

// Strip macOS-native optional packages (e.g. sharp's darwin libvips binaries)
// that Next traces in. The app uses plain <img> (images.unoptimized), so these
// are never loaded — but removing them guarantees a Mac-built bundle ships zero
// macOS-only native code and runs cleanly on the Linux cPanel host.
execFileSync(
  'find',
  [standaloneDir, '-type', 'd', '-name', '*darwin*', '-prune', '-exec', 'rm', '-rf', '{}', '+'],
  { stdio: 'inherit' },
);

// Passenger startup shim at the bundle root. cPanel's "Setup Node.js App"
// points its startup file here; Passenger provides PORT via env.
//
// The Next standalone server.js is an ES module, so the shim loads it with a
// dynamic import() rather than require() — require() of ESM throws on Node 20
// (the cPanel runtime), even though Node 22+ permits it.
writeFileSync(
  path.join(standaloneDir, 'app.js'),
  [
    "process.chdir(__dirname + '/apps/web');",
    "import('./apps/web/server.js').catch((err) => {",
    '  console.error(err);',
    '  process.exit(1);',
    '});',
    '',
  ].join('\n'),
);

mkdirSync(distDir, { recursive: true });
rmSync(zipPath, { force: true });
execFileSync('zip', ['-qry', zipPath, '.'], { cwd: standaloneDir, stdio: 'inherit' });

console.log(`cPanel bundle ready: ${path.relative(appDir, zipPath)}`);
console.log('Runnable locally:    PORT=3000 node .next/standalone/app.js');
