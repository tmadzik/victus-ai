import path from 'node:path';
import { fileURLToPath } from 'node:url';

import type { NextConfig } from 'next';

const monorepoRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), '../..');

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Self-contained production server for cPanel (Passenger / "Setup Node.js
  // App") — `pnpm build:cpanel` packages .next/standalone into a deployable
  // bundle with node_modules included, so the host never runs `npm install`.
  output: 'standalone',
  outputFileTracingRoot: monorepoRoot,
  experimental: {
    typedRoutes: true,
  },
  transpilePackages: ['@victus/ui'],
  async headers() {
    const securityHeaders: { key: string; value: string }[] = [
      { key: 'X-DNS-Prefetch-Control', value: 'on' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      {
        key: 'Permissions-Policy',
        value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()',
      },
    ];
    // HSTS is correct in production (Caddy terminates TLS) but POISONOUS over
    // plain HTTP on localhost: the browser pins the whole `localhost` host —
    // every port, via includeSubDomains — to https, and since nothing serves TLS
    // locally every page then fails to connect. The pin survives a hard reload
    // and outlives the demo. So the local build omits it.
    if (process.env.VICTUS_DISABLE_HSTS !== '1') {
      securityHeaders.push({
        key: 'Strict-Transport-Security',
        value: 'max-age=63072000; includeSubDomains; preload',
      });
    }
    return [
      {
        source: '/(.*)',
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
