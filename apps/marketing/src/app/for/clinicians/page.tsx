import { ClipboardList, FileDown, Send, Stethoscope, TrendingUp, UserSearch } from 'lucide-react';
import type { Metadata } from 'next';
import type { ReactElement } from 'react';

import { RoleLanding } from '@/components/role-landing';
import { APP_URL } from '@/lib/site';

export const metadata: Metadata = {
  title: 'For clinicians & care teams',
  description:
    'Victus for clinicians: see who needs attention first, review a participant’s full screening history, raise referrals and export the record as a PDF.',
  alternates: { canonical: '/for/clinicians' },
};

export default function CliniciansPage(): ReactElement {
  return (
    <RoleLanding
      eyebrow="For clinicians & care teams"
      title="See who needs you first."
      intro="Victus turns a five-minute screen into a clear picture of who in front of you needs attention now — and gives you the record, the referral and the paperwork to act on it in the same visit."
      features={[
        {
          title: 'A clear result per person',
          description:
            'Every screen resolves to low risk, watch, or urgent referral — with genuinely uncertain cases sent to you for a human check rather than quietly guessed at.',
          icon: Stethoscope,
        },
        {
          title: 'Danger signs never buried',
          description:
            'Red-flag symptoms escalate on fixed clinical rules, independently of what the model predicts. The model is never the last line of defence.',
          icon: TrendingUp,
        },
        {
          title: 'One participant record',
          description:
            'Find a participant and see their identified record with every previous assessment across both screening pathways, in one timeline.',
          icon: UserSearch,
        },
        {
          title: 'Referrals that get followed',
          description:
            'Raise a referral with an urgency, to a Victus facility or a partner or public clinic, and track it through acknowledged to completed.',
          icon: Send,
        },
        {
          title: 'Export for the file',
          description:
            'Download the participant record as a PDF for your own notes, the patient, or the receiving clinic.',
          icon: FileDown,
        },
        {
          title: 'Every access accounted for',
          description:
            'Opening an identified record is role-restricted and written to an audit log — so you can show exactly who saw what, and when.',
          icon: ClipboardList,
        },
      ]}
      primary={{ label: 'Sign in', href: `${APP_URL}/login?role=clinician` }}
      secondary={{
        label: 'Request access',
        note: 'Clinician accounts are provisioned through your organisation — tell us about your team and we’ll set you up.',
      }}
    />
  );
}
