'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { UserRole } from '@victus/contracts';

import { LanguageSwitcher } from '@/components/language-switcher';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Locale } from '@/i18n/config';
import type { Dictionary } from '@/i18n/dictionaries/en';
import { cn } from '@/lib/utils';
import { logoutAction } from '@/server/auth-actions';

import { NotificationBell } from './notification-bell';

type NavHref =
  | '/dashboard'
  | '/triage'
  | '/toi'
  | '/history'
  | '/referrals'
  | '/clinical'
  | '/research'
  | '/account/data'
  | '/admin/governance';

type NavKey = keyof Dictionary['nav'];
type NavItem = { href: NavHref; key: NavKey };

const NAV: NavItem[] = [
  { href: '/dashboard', key: 'dashboard' },
  { href: '/triage', key: 'triage' },
  { href: '/toi', key: 'toi' },
  { href: '/history', key: 'history' },
  { href: '/referrals', key: 'referrals' },
  { href: '/account/data', key: 'data' },
];

// Clinicians / admins can open any participant's identified record.
const CLINICAL_NAV: NavItem[] = [{ href: '/clinical', key: 'clinical' }];

// Researchers (CHW / clinician / admin) get the labelled-data capture console.
const RESEARCH_NAV: NavItem[] = [{ href: '/research', key: 'research' }];

const ADMIN_NAV: NavItem[] = [{ href: '/admin/governance', key: 'admin' }];

const RESEARCHER_ROLES: readonly UserRole[] = [
  UserRole.CHW,
  UserRole.CLINICIAN,
  UserRole.ADMIN,
];

export function AppShell({
  user,
  unreadCount,
  locale,
  nav,
  languageLabel,
  previewNote,
  children,
}: {
  user: { name: string; role: UserRole };
  unreadCount: number;
  locale: Locale;
  nav: Dictionary['nav'];
  languageLabel: string;
  previewNote: string;
  children: React.ReactNode;
}): React.ReactElement {
  const pathname = usePathname();
  const isClinical = user.role === UserRole.CLINICIAN || user.role === UserRole.ADMIN;
  const navItems = [
    ...NAV,
    ...(isClinical ? CLINICAL_NAV : []),
    ...(RESEARCHER_ROLES.includes(user.role) ? RESEARCH_NAV : []),
    ...(user.role === UserRole.ADMIN ? ADMIN_NAV : []),
  ];

  return (
    <div className="flex min-h-dvh flex-col">
      {locale !== 'en' ? (
        <div className="bg-brand-100 px-6 py-1.5 text-center text-xs text-brand-800">
          {previewNote}
        </div>
      ) : null}
      <header className="border-b border-brand-100 bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link
            href="/dashboard"
            className="flex items-center"
            aria-label="Victus AI — go to dashboard"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/victus-logo.svg" alt="Victus AI" className="h-9 w-auto" />
          </Link>
          <nav aria-label="Primary" className="hidden gap-1 md:flex">
            {navItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'rounded-[var(--radius-control)] px-3 py-2 text-sm font-medium transition-colors',
                    active
                      ? 'bg-brand-100 text-brand-900'
                      : 'text-brand-700 hover:bg-brand-50 hover:text-brand-900',
                  )}
                >
                  {nav[item.key]}
                </Link>
              );
            })}
          </nav>
          <div className="flex items-center gap-3">
            <LanguageSwitcher current={locale} label={languageLabel} />
            <NotificationBell initialCount={unreadCount} />
            <div className="hidden text-right text-xs leading-tight sm:block">
              <p className="font-medium text-brand-900">{user.name}</p>
              <Badge tone="brand">{user.role}</Badge>
            </div>
            <form action={logoutAction}>
              <Button type="submit" size="sm" variant="outline">
                {nav.signOut}
              </Button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
      <footer className="border-t border-brand-100 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4 text-xs text-brand-600">
          <p>© Victus AI — Research preview</p>
          <p>POPIA · audit logging active</p>
        </div>
      </footer>
    </div>
  );
}
