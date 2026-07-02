import { redirect } from 'next/navigation';

import { UserRole } from '@victus/contracts';

import { getI18n } from '@/i18n';
import { DictionaryProvider } from '@/i18n/context';
import { apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { AppShell } from './app-shell';

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login');
  }
  if (session.error === 'refresh_failed') {
    redirect('/login?reason=session_expired');
  }

  // Enrollment gate: participants must complete the front-of-platform intake
  // (identified demographics + consent) before reaching any pathway. Clinicians
  // and admins are not participants and are exempt. (redirect() stays out of the
  // try/catch so its control-flow throw isn't swallowed.)
  if (session.user.role === UserRole.PATIENT) {
    let enrolled = false;
    try {
      enrolled = (await apiClient.getEnrollmentStatus(session.accessToken)).enrolled;
    } catch {
      enrolled = false;
    }
    if (!enrolled) redirect('/enroll');
  }

  // Unread badge for the header bell. Best-effort — a notification fetch
  // failure must never block rendering the app.
  let unreadCount = 0;
  try {
    const { unread_count } = await apiClient.getUnreadCount(session.accessToken);
    unreadCount = unread_count;
  } catch {
    unreadCount = 0;
  }

  const { locale, dict } = await getI18n();

  return (
    <DictionaryProvider dict={dict} locale={locale}>
      <AppShell
        user={{
          name: session.user.name ?? session.user.email ?? 'Account',
          role: session.user.role,
        }}
        unreadCount={unreadCount}
        locale={locale}
        nav={dict.nav}
        languageLabel={dict.language.label}
        previewNote={dict.language.previewNote}
      >
        {children}
      </AppShell>
    </DictionaryProvider>
  );
}
