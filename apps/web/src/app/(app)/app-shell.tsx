'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { UserRole } from '@victus/contracts';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { logoutAction } from '@/server/auth-actions';

import { NotificationBell } from './notification-bell';

type NavHref =
  | '/dashboard'
  | '/triage'
  | '/toi'
  | '/history'
  | '/clinical'
  | '/research'
  | '/account/data'
  | '/admin/governance';

const NAV: { href: NavHref; label: string }[] = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/triage', label: 'Pathway A — Triage' },
  { href: '/toi', label: 'Pathway B — TOI' },
  { href: '/history', label: 'History' },
  { href: '/account/data', label: 'Data & erasure' },
];

// Clinicians / admins can open any participant's identified record.
const CLINICAL_NAV: { href: NavHref; label: string }[] = [
  { href: '/clinical', label: 'Clinical' },
];

// Researchers (CHW / clinician / admin) get the labelled-data capture console.
const RESEARCH_NAV: { href: NavHref; label: string }[] = [
  { href: '/research', label: 'Research' },
];

const ADMIN_NAV: { href: NavHref; label: string }[] = [
  { href: '/admin/governance', label: 'Admin' },
];

const RESEARCHER_ROLES: readonly UserRole[] = [
  UserRole.CHW,
  UserRole.CLINICIAN,
  UserRole.ADMIN,
];

export function AppShell({
  user,
  unreadCount,
  children,
}: {
  user: { name: string; role: UserRole };
  unreadCount: number;
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
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="flex items-center gap-3">
            <NotificationBell initialCount={unreadCount} />
            <div className="hidden text-right text-xs leading-tight sm:block">
              <p className="font-medium text-brand-900">{user.name}</p>
              <Badge tone="brand">{user.role}</Badge>
            </div>
            <form action={logoutAction}>
              <Button type="submit" size="sm" variant="outline">
                Sign out
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
