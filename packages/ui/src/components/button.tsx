import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type ButtonHTMLAttributes } from 'react';

import { cn } from '../lib/cn';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] text-sm font-medium ring-offset-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800',
        secondary: 'bg-brand-100 text-brand-900 hover:bg-brand-200 active:bg-brand-300',
        outline:
          'border border-brand-300 bg-white text-brand-900 hover:bg-brand-50 active:bg-brand-100',
        ghost: 'text-brand-900 hover:bg-brand-50 active:bg-brand-100',
        danger:
          'bg-[color:var(--color-state-red-ring)] text-white shadow-sm hover:opacity-90 active:opacity-80',
      },
      size: {
        sm: 'h-9 px-3 text-xs',
        md: 'h-10 px-4 py-2',
        lg: 'h-12 px-6 text-base',
        icon: 'h-10 w-10 p-0',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />
    );
  },
);
Button.displayName = 'Button';

export { buttonVariants };
