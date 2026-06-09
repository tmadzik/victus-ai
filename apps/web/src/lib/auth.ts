import NextAuth, { type DefaultSession, type NextAuthConfig } from 'next-auth';
import Credentials from 'next-auth/providers/credentials';

import {
  type ConsentType,
  LoginRequestSchema,
  type UserRole,
} from '@victus/contracts';

import { apiClient, ApiError } from './api-client';
import { serverEnv } from './env';

declare module 'next-auth' {
  interface Session {
    user: DefaultSession['user'] & {
      id: string;
      role: UserRole;
      consents: ConsentType[];
    };
    accessToken: string;
    error?: 'refresh_failed';
  }
}

// next-auth re-exports its JWT type from @auth/core/jwt; under pnpm +
// moduleResolution "Bundler" the `next-auth/jwt` subpath is not resolvable as
// an augmentation target, so we augment the source module that actually
// declares the interface (added as a direct dependency for this reason).
declare module '@auth/core/jwt' {
  interface JWT {
    userId: string;
    role: UserRole;
    consents: ConsentType[];
    email: string;
    name: string;
    accessToken: string;
    refreshToken: string;
    accessTokenExpiresAt: number;
    error?: 'refresh_failed';
  }
}

const REFRESH_LEEWAY_SECONDS = 30;

const config: NextAuthConfig = {
  secret: serverEnv.AUTH_SECRET,
  trustHost: serverEnv.AUTH_TRUST_HOST ?? false,
  session: { strategy: 'jwt' },
  pages: {
    signIn: '/login',
    error: '/login',
  },
  providers: [
    Credentials({
      name: 'Victus Credentials',
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(raw) {
        const parsed = LoginRequestSchema.safeParse(raw);
        if (!parsed.success) return null;
        try {
          const session = await apiClient.login(parsed.data);
          const expiresAt = Math.floor(Date.now() / 1000) + session.tokens.expires_in;
          return {
            id: session.user.id,
            email: session.user.email,
            name: session.user.full_name,
            role: session.user.role,
            consents: session.user.consents,
            accessToken: session.tokens.access_token,
            refreshToken: session.tokens.refresh_token,
            accessTokenExpiresAt: expiresAt,
          } as unknown as import('next-auth').User;
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) return null;
          throw err;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user, trigger }) {
      if (user) {
        const enriched = user as unknown as {
          id: string;
          email: string;
          name: string;
          role: UserRole;
          consents: ConsentType[];
          accessToken: string;
          refreshToken: string;
          accessTokenExpiresAt: number;
        };
        token.userId = enriched.id;
        token.email = enriched.email;
        token.name = enriched.name;
        token.role = enriched.role;
        token.consents = enriched.consents;
        token.accessToken = enriched.accessToken;
        token.refreshToken = enriched.refreshToken;
        token.accessTokenExpiresAt = enriched.accessTokenExpiresAt;
        return token;
      }

      if (trigger === 'update') {
        try {
          const me = await apiClient.me(token.accessToken);
          token.role = me.role;
          token.consents = me.consents;
        } catch {
          // tolerate transient failures; client will retry on next nav
        }
      }

      const now = Math.floor(Date.now() / 1000);
      if (token.accessTokenExpiresAt - REFRESH_LEEWAY_SECONDS > now) {
        return token;
      }

      try {
        const refreshed = await apiClient.refresh(token.refreshToken);
        token.accessToken = refreshed.tokens.access_token;
        token.refreshToken = refreshed.tokens.refresh_token;
        token.accessTokenExpiresAt =
          Math.floor(Date.now() / 1000) + refreshed.tokens.expires_in;
        token.role = refreshed.user.role;
        token.consents = refreshed.user.consents;
        token.error = undefined;
      } catch {
        token.error = 'refresh_failed';
      }
      return token;
    },
    async session({ session, token }) {
      session.user = {
        ...session.user,
        id: token.userId,
        email: token.email,
        name: token.name,
        role: token.role,
        consents: token.consents,
      };
      session.accessToken = token.accessToken;
      session.error = token.error;
      return session;
    },
    authorized({ auth, request }) {
      const { pathname } = request.nextUrl;
      const publicPaths = ['/login', '/register', '/'];
      const isPublic =
        publicPaths.includes(pathname) ||
        pathname.startsWith('/api/auth') ||
        pathname.startsWith('/_next') ||
        pathname.startsWith('/favicon');
      if (isPublic) return true;
      return Boolean(auth?.user);
    },
  },
};

export const { auth, handlers, signIn, signOut, unstable_update } =
  NextAuth(config);
