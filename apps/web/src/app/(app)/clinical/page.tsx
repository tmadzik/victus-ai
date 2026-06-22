import Link from 'next/link';
import { redirect } from 'next/navigation';

import { type ParticipantSummary, UserRole } from '@victus/contracts';

import { Card, CardContent } from '@/components/ui/card';
import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export const metadata = { title: 'Participant review — Victus AI' };

const CLINICAL_ROLES: readonly UserRole[] = [UserRole.CLINICIAN, UserRole.ADMIN];

export default async function ClinicalPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');
  if (!CLINICAL_ROLES.includes(session.user.role)) redirect('/dashboard');

  const { q } = await searchParams;
  const query = (q ?? '').trim();

  let results: ParticipantSummary[] | null = null;
  let error: string | null = null;
  if (query.length > 0) {
    try {
      results = await apiClient.searchParticipants(session.accessToken, query, 50);
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Search failed. Please try again.';
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Clinician review
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Participant review
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">
          Search a participant by name or email to open their identified
          assessment record. Every search and record view is written to the audit
          log.
        </p>
      </header>

      <form method="get" className="flex gap-2">
        <input
          type="search"
          name="q"
          defaultValue={query}
          placeholder="Name or email…"
          aria-label="Search participants"
          className="w-full max-w-md rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-900 outline-none focus:border-brand-500"
        />
        <button
          type="submit"
          className="rounded-[var(--radius-control)] bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Search
        </button>
      </form>

      {error ? (
        <Card>
          <CardContent className="py-6 text-sm text-rose-700">{error}</CardContent>
        </Card>
      ) : results === null ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-brand-600">
            Enter a name or email above to find a participant.
          </CardContent>
        </Card>
      ) : results.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-brand-600">
            No participants match “{query}”.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-brand-100 text-xs uppercase tracking-wider text-brand-600">
                <tr>
                  <th className="px-4 py-3">Participant</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Triage</th>
                  <th className="px-4 py-3">TOI</th>
                  <th className="px-4 py-3">Last activity</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {results.map((p) => (
                  <tr key={p.user_id} className="border-b border-brand-50 last:border-0">
                    <td className="px-4 py-3">
                      <div className="font-medium text-brand-900">
                        {p.full_name ?? '—'}
                      </div>
                      <div className="text-xs text-brand-600">{p.email ?? '—'}</div>
                    </td>
                    <td className="px-4 py-3 text-brand-700">{p.role}</td>
                    <td className="px-4 py-3 font-mono text-brand-900">{p.triage_count}</td>
                    <td className="px-4 py-3 font-mono text-brand-900">{p.toi_count}</td>
                    <td className="px-4 py-3 text-xs text-brand-600">
                      {p.last_activity
                        ? new Date(p.last_activity).toLocaleDateString('en-ZA', {
                            dateStyle: 'medium',
                          })
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/clinical/${p.user_id}`}
                        className="font-medium text-brand-700 hover:text-brand-900"
                      >
                        Open record →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
