# Victus clinical web app — Next.js 15 (standalone output).
#
# Build context is the MONOREPO ROOT (the app depends on the @victus/contracts
# and @victus/ui workspace packages), so build with:
#   docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_BASE_URL=... .
# The compose file wires this up automatically.

FROM node:20-slim AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable
WORKDIR /repo

FROM base AS build
# The browser-facing API URL is baked in at build time (NEXT_PUBLIC_*), so it
# must be the PUBLIC https://api.<domain> — not the internal service address.
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
# The web app validates runtime env at build unless told to skip; server-only
# secrets (AUTH_SECRET, INTERNAL_SERVICE_TOKEN) are injected at run time.
ENV SKIP_ENV_VALIDATION=1
COPY . .
RUN pnpm install --frozen-lockfile \
    && pnpm --filter @victus/web build

FROM node:20-slim AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
# Next standalone server + its traced node_modules, then the static assets and
# public/ (which the standalone server does not copy itself).
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /repo/apps/web/public ./apps/web/public
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
