/**
 * Assembles the Next.js standalone output into a self-contained cPanel
 * deployment bundle. Run via `pnpm build:cpanel` (chains after `next build`).
 *
 * Produces:
 *   .next/standalone/                            runnable in place (`pnpm start`)
 *   dist-cpanel/victus-marketing-cpanel.tar.gz   upload to cPanel
 *
 * Ships as .tar.gz, not .zip: cPanel's ClamAV + Sanesecurity "Foxhole" ruleset
 * flags ANY zip containing JavaScript (Foxhole.JS_Zip_*) as a false positive,
 * which a Node bundle always trips. cPanel's File Manager extracts .tar.gz the
 * same way (right-click -> Extract).
 *
 * Bundle layout (archive root = Passenger application root):
 *   app.js                       Passenger startup file
 *   apps/marketing/server.js    Next standalone server (used by app.js)
 *   apps/marketing/.next/...     compiled app + static assets
 *   apps/marketing/public/...    public assets
 *   node_modules/...             traced production dependencies
 */

import { execFileSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const appDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const standaloneDir = path.join(appDir, '.next', 'standalone');
const appInStandalone = path.join(standaloneDir, 'apps', 'marketing');
const distDir = path.join(appDir, 'dist-cpanel');
const tgzPath = path.join(distDir, 'victus-marketing-cpanel.tar.gz');

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

// Passenger startup shim at the bundle root. cPanel's "Setup Node.js App"
// points its startup file here; Passenger provides PORT via env.
//
// The Next standalone server.js is an ES module, so the shim loads it with a
// dynamic import() rather than require() — require() of ESM throws on Node 20
// (the cPanel runtime), even though Node 22+ permits it.
writeFileSync(
  path.join(standaloneDir, 'app.js'),
  [
    "process.chdir(__dirname + '/apps/marketing');",
    "import('./apps/marketing/server.js').catch((err) => {",
    '  console.error(err);',
    '  process.exit(1);',
    '});',
    '',
  ].join('\n'),
);

mkdirSync(distDir, { recursive: true });
rmSync(tgzPath, { force: true });
// Also clear any stale .zip from the previous packaging format.
rmSync(path.join(distDir, 'victus-marketing-cpanel.zip'), { force: true });
execFileSync('tar', ['-czf', tgzPath, '-C', standaloneDir, '.'], { stdio: 'inherit' });

console.log(`cPanel bundle ready: ${path.relative(appDir, tgzPath)}`);
console.log('Runnable locally:    PORT=3001 node .next/standalone/app.js');
