import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes, ReactElement } from 'react';

import { TriageState } from '@victus/contracts';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider',
  {
    variants: {
      tone: {
        neutral: 'border-brand-200 bg-brand-50 text-brand-800',
        brand: 'border-brand-500 bg-brand-100 text-brand-900',
        green:
          'border-[color:var(--color-state-green-ring)] bg-[color:var(--color-state-green-bg)] text-[color:var(--color-state-green-fg)]',
        yellow:
          'border-[color:var(--color-state-yellow-ring)] bg-[color:var(--color-state-yellow-bg)] text-[color:var(--color-state-yellow-fg)]',
        red: 'border-[color:var(--color-state-red-ring)] bg-[color:var(--color-state-red-bg)] text-[color:var(--color-state-red-fg)]',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps): ReactElement {
  return <span className={cn(badgeVariants({ tone, className }))} {...props} />;
}

const STATE_TONE: Record<TriageState, NonNullable<BadgeProps['tone']>> = {
  [TriageState.GREEN]: 'green',
  [TriageState.YELLOW]: 'yellow',
  [TriageState.RED]: 'red',
};

const STATE_LABEL: Record<TriageState, string> = {
  [TriageState.GREEN]: 'Low risk',
  [TriageState.YELLOW]: 'Uncertain — audit required',
  [TriageState.RED]: 'Urgent clinical referral',
};

export function TriageStateBadge({ state }: { state: TriageState }): ReactElement {
  return (
    <Badge tone={STATE_TONE[state]} aria-label={`Triage state: ${STATE_LABEL[state]}`}>
      <span aria-hidden="true">{state}</span>
      <span className="sr-only">{STATE_LABEL[state]}</span>
    </Badge>
  );
}
