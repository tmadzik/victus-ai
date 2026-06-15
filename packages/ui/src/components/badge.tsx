import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes, ReactElement } from 'react';

import { cn } from '../lib/cn';

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
  extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps): ReactElement {
  return <span className={cn(badgeVariants({ tone, className }))} {...props} />;
}

export { badgeVariants };
