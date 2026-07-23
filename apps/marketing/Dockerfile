# Victus marketing site (www.victusdata.com) — Next.js 15 (standalone output).
#
# Build context is the MONOREPO ROOT (depends on the @victus/ui workspace
# package). The compose file wires this up automatically.

FROM node:20-slim AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable
WORKDIR /repo

FROM base AS build
# Link target for "Launch the platform" CTAs — the public clinical-app URL.
ARG NEXT_PUBLIC_APP_URL
ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL
ENV SKIP_ENV_VALIDATION=1
# Omit the HSTS header in local/demo builds — over plain HTTP it pins the
# whole localhost host to https and every page then fails to connect.
ARG VICTUS_DISABLE_HSTS=0
ENV VICTUS_DISABLE_HSTS=$VICTUS_DISABLE_HSTS
COPY . .
RUN pnpm install --frozen-lockfile \
    && pnpm --filter @victus/marketing build

FROM node:20-slim AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build /repo/apps/marketing/.next/standalone ./
COPY --from=build /repo/apps/marketing/.next/static ./apps/marketing/.next/static
COPY --from=build /repo/apps/marketing/public ./apps/marketing/public
USER node
EXPOSE 3000
CMD ["node", "apps/marketing/server.js"]
