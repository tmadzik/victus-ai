import { redirect } from 'next/navigation';

import { UserRole } from '@victus/contracts';

import { apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { EnrollForm } from './enroll-form';

export const metadata = { title: 'Enrollment — Victus AI' };

/**
 * Front-of-platform enrollment gate. Every participant completes this before
 * reaching the pathways. Clinicians/admins are not participants — they skip it.
 */
export default async function EnrollPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');
  if (session.user.role !== UserRole.PATIENT) redirect('/dashboard');

  // If already enrolled, don't re-capture. (redirect() must stay out of try/catch.)
  let enrolled = false;
  try {
    enrolled = (await apiClient.getEnrollmentStatus(session.accessToken)).enrolled;
  } catch {
    enrolled = false;
  }
  if (enrolled) redirect('/dashboard');

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col justify-center px-5 py-10">
      <EnrollForm />
    </main>
  );
}
