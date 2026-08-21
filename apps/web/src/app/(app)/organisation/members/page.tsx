import Link from 'next/link';
import { redirect } from 'next/navigation';

import { type FlaggedMemberList, UserRole } from '@victus/contracts';

import { Card, CardContent } from '@/components/ui/card';
import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { AttestForm } from './attest-form';

export const metadata = { title: 'Flagged members' };

const STATE_TONE: Record<string, string> = {
  RED: 'bg-red-50 text-red-800 ring-red-200',
  YELLOW: 'bg-amber-50 text-amber-800 ring-amber-200',
  GREEN: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
};

export default async function FlaggedMembersPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');
  // Care managers only. An organisation admin is not redirected somewhere
  // vague — they are told plainly below that this view is not theirs, because
  // silently bouncing someone teaches them nothing about why.
  if (
    session.user.role !== UserRole.CARE_MANAGER &&
    session.user.role !== UserRole.ADMIN
  ) {
    redirect('/organisation');
  }

  const status = await apiClient
    .getAttestationStatus(session.accessToken)
    .catch(() => null);

  let members: FlaggedMemberList | null = null;
  let error: string | null = null;
  if (status?.active) {
    try {
      members = await apiClient.getFlaggedMembers(session.accessToken);
    } catch (err) {
      error =
        err instanceof ApiError ? err.message : 'Could not load the member list.';
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Care routing
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Flagged members
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">
          Members whose most recent screening returned urgent or watch. Use this
          to follow up individually &mdash; a wellness referral, a call, a clinic
          appointment.
        </p>
        <p className="mt-2 max-w-2xl text-sm text-brand-600">
          Screening indicates who may need attention. It is not a diagnosis, and
          it is not a basis for any decision about a member&apos;s cover.
        </p>
      </header>

      {!status ? (
        <Card>
          <CardContent className="py-6">
            <p className="text-brand-800">
              Could not check your confirmation status. Please reload.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {status && !status.active ? <AttestForm text={status.text} /> : null}

      {error ? (
        <Card>
          <CardContent className="py-6">
            <p className="text-brand-800">{error}</p>
          </CardContent>
        </Card>
      ) : null}

      {members ? (
        <Card>
          <CardContent className="py-6">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="text-sm font-semibold text-brand-950">
                {members.count} member{members.count === 1 ? '' : 's'} flagged
              </h2>
              {status?.expires_at ? (
                <p className="text-xs text-brand-600">
                  Your confirmation lasts until{' '}
                  {new Date(status.expires_at).toLocaleDateString()}
                </p>
              ) : null}
            </div>

            {members.count === 0 ? (
              <p className="mt-4 text-sm text-brand-700">
                Nobody is currently flagged.
              </p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-brand-200 text-xs uppercase tracking-[0.12em] text-brand-600">
                      <th scope="col" className="pb-2 pr-4 font-semibold">
                        Member
                      </th>
                      <th scope="col" className="pb-2 pr-4 font-semibold">
                        State
                      </th>
                      <th scope="col" className="pb-2 font-semibold">
                        Screened
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.members.map((m) => (
                      <tr key={m.user_id} className="border-b border-brand-100">
                        <td className="py-3 pr-4">
                          <Link
                            href={`/clinical/${m.user_id}`}
                            className="font-medium text-brand-800 underline-offset-4 hover:underline"
                          >
                            {m.user_id.slice(0, 8)}
                          </Link>
                        </td>
                        <td className="py-3 pr-4">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${
                              STATE_TONE[m.triage_state] ?? 'bg-brand-50 text-brand-800 ring-brand-200'
                            }`}
                          >
                            {m.triage_state}
                          </span>
                        </td>
                        <td className="py-3 tabular-nums text-brand-700">
                          {new Date(m.assessed_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="mt-5 text-xs text-brand-500">
              Opening this list is recorded in the audit log against your name.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
