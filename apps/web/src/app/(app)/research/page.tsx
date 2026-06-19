import Link from 'next/link';
import { redirect } from 'next/navigation';

import {
  DISEASES,
  DISEASE_LABELS,
  type ResearchCaseResponse,
  type ResearchCorpusStats,
  RISK_CLASSES,
  type RiskClass,
  UserRole,
} from '@victus/contracts';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { ResearchCaptureForm } from './research-client';

export const metadata = { title: 'Research console' };

const RESEARCHER_ROLES: readonly UserRole[] = [
  UserRole.CHW,
  UserRole.CLINICIAN,
  UserRole.ADMIN,
];

const RISK_SHORT: Record<RiskClass, string> = {
  LOW_RISK: 'Low',
  ELEVATED_RISK: 'Elev',
  HIGH_RISK: 'High',
  VERY_HIGH_RISK: 'V.High',
};

const RISK_BAR: Record<RiskClass, string> = {
  LOW_RISK: 'bg-emerald-500',
  ELEVATED_RISK: 'bg-amber-400',
  HIGH_RISK: 'bg-orange-500',
  VERY_HIGH_RISK: 'bg-rose-600',
};

export default async function ResearchPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');
  if (!RESEARCHER_ROLES.includes(session.user.role)) redirect('/dashboard');

  const [stats, cases] = await Promise.all([
    apiClient.getResearchStats(session.accessToken),
    apiClient.listResearchCases(session.accessToken, 25),
  ]);

  return (
    <div className="space-y-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            Research console
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
            Labelled triage corpus
          </h1>
          <p className="mt-2 max-w-2xl text-brand-700">
            Ground-truth-labelled cases that train Pathway A on recruited data.
            Diabetes labels are anchored on HbA1c / fasting glucose — the signal
            the proxy model never had.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/toi/calibration">TOI calibration →</Link>
          </Button>
        </div>
      </header>

      <Dashboard stats={stats} />

      <ResearchCaptureForm />

      <RecentCases cases={cases} />
    </div>
  );
}

function Dashboard({ stats }: { stats: ResearchCorpusStats }): React.ReactElement {
  const domainEntries = Object.entries(stats.by_domain);
  return (
    <section className="grid gap-4 lg:grid-cols-[repeat(3,minmax(0,1fr))]">
      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle className="text-lg">Corpus snapshot</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Metric label="Total cases" value={String(stats.total)} />
            <Metric label="With BP reading" value={String(stats.with_bp)} />
            <Metric label="With glucose marker" value={String(stats.with_diabetes_marker)} />
            <Metric
              label="Domains"
              value={
                domainEntries.length === 0
                  ? '—'
                  : domainEntries.map(([k, v]) => `${k.split('_')[0]} ${v}`).join(' · ')
              }
            />
          </dl>
        </CardContent>
      </Card>

      {DISEASES.map((disease) => (
        <DiseaseDistribution
          key={disease}
          title={DISEASE_LABELS[disease]}
          dist={
            disease === 'OBESITY'
              ? stats.label_distribution.obesity
              : disease === 'HYPERTENSION'
                ? stats.label_distribution.hypertension
                : stats.label_distribution.diabetes
          }
          total={stats.total}
        />
      ))}
    </section>
  );
}

function DiseaseDistribution({
  title,
  dist,
  total,
}: {
  title: string;
  dist: Record<string, number>;
  total: number;
}): React.ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {RISK_CLASSES.map((cls) => {
          const n = dist[cls] ?? 0;
          const pct = total > 0 ? (n / total) * 100 : 0;
          return (
            <div key={cls}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="text-brand-700">{RISK_SHORT[cls]}</span>
                <span className="font-mono text-brand-700">{n}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-brand-100">
                <div className={`h-full ${RISK_BAR[cls]}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function RecentCases({
  cases,
}: {
  cases: ResearchCaseResponse[];
}): React.ReactElement {
  if (cases.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-brand-600">
          No cases yet — record the first one above.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Recent cases</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wider text-brand-600">
            <tr>
              <th className="pb-2">When</th>
              <th className="pb-2">Domain</th>
              <th className="pb-2">BMI</th>
              <th className="pb-2">Obesity</th>
              <th className="pb-2">Hypertension</th>
              <th className="pb-2">Diabetes</th>
            </tr>
          </thead>
          <tbody className="font-mono text-xs text-brand-900">
            {cases.map((c) => (
              <tr key={c.id} className="border-t border-brand-100">
                <td className="py-2 pr-3">
                  {new Date(c.created_at).toLocaleString('en-ZA', {
                    dateStyle: 'short',
                    timeStyle: 'short',
                  })}
                </td>
                <td className="py-2 pr-3">{c.capture_domain.split('_')[0]}</td>
                <td className="py-2 pr-3">{c.bmi}</td>
                <td className="py-2 pr-3">{RISK_SHORT[c.obesity_label]}</td>
                <td className="py-2 pr-3">{RISK_SHORT[c.hypertension_label]}</td>
                <td className="py-2 pr-3">{RISK_SHORT[c.diabetes_label]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-3">
      <dt className="text-xs font-semibold uppercase tracking-wider text-brand-700">
        {label}
      </dt>
      <dd className="mt-1 font-mono text-base text-brand-950">{value}</dd>
    </div>
  );
}
