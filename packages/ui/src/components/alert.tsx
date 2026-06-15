import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type HTMLAttributes } from 'react';

import { cn } from '../lib/cn';

const alertVariants = cva(
  'relative w-full rounded-[var(--radius-card)] border p-4 text-sm [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg+div]:translate-y-[-3px] [&>svg~*]:pl-7',
  {
    variants: {
      tone: {
        info: 'border-brand-200 bg-brand-50 text-brand-900',
        success:
          'border-[color:var(--color-state-green-ring)]/40 bg-[color:var(--color-state-green-bg)] text-[color:var(--color-state-green-fg)]',
        warning:
          'border-[color:var(--color-state-yellow-ring)]/50 bg-[color:var(--color-state-yellow-bg)] text-[color:var(--color-state-yellow-fg)]',
        danger:
          'border-[color:var(--color-state-red-ring)]/50 bg-[color:var(--color-state-red-bg)] text-[color:var(--color-state-red-fg)]',
      },
    },
    defaultVariants: { tone: 'info' },
  },
);

export interface AlertProps
  extends HTMLAttributes<HTMLDivElement>, VariantProps<typeof alertVariants> {}

export const Alert = forwardRef<HTMLDivElement, AlertProps>(
  ({ className, tone, ...props }, ref) => (
    <div ref={ref} role="alert" className={cn(alertVariants({ tone, className }))} {...props} />
  ),
);
Alert.displayName = 'Alert';

export const AlertTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h5
      ref={ref}
      className={cn('mb-1 leading-none font-semibold tracking-tight', className)}
      {...props}
    />
  ),
);
AlertTitle.displayName = 'AlertTitle';

export const AlertDescription = forwardRef<
  HTMLParagraphElement,
  HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('text-sm leading-relaxed [&_p]:leading-relaxed', className)}
    {...props}
  />
));
AlertDescription.displayName = 'AlertDescription';
