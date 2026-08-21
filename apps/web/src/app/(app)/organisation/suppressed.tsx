import type { ReactElement } from 'react';

import { cn } from '@victus/ui';

/**
 * Renders one possibly-suppressed count.
 *
 * The whole reason this is a component rather than `{value ?? 0}` at each call
 * site: `null` means *withheld because too few people are in this cell*, and
 * zero means *nobody is in this cell*. Rendering a suppressed cell as "0" would
 * be the most damaging bug on this page — it turns "we are not telling you"
 * into "there is nobody here", and a funder reading a dashboard showing zero
 * high-risk members would reasonably conclude they have none.
 *
 * So a suppressed cell renders as a visibly different thing, not a number.
 */
export function SuppressedCount({
  value,
  className,
}: {
  value: number | null;
  className?: string;
}): ReactElement {
  if (value === null) {
    return (
      <span
        className={cn('inline-flex items-baseline gap-1.5 text-brand-500', className)}
        title="Withheld: fewer than the minimum number of members in this group."
      >
        <span aria-hidden className="font-semibold tracking-tight">
          &mdash;
        </span>
        <span className="sr-only">Withheld — too few members to show</span>
      </span>
    );
  }
  return (
    <span className={cn('tabular-nums font-semibold tracking-tight', className)}>
      {value.toLocaleString()}
    </span>
  );
}

/**
 * A labelled row of possibly-suppressed counts, e.g. a triage distribution.
 * Cells keep a stable order so the shape of the breakdown does not jump around
 * between refreshes as suppression moves.
 */
export function SuppressedBreakdown({
  title,
  cells,
  order,
  tone,
}: {
  title: string;
  cells: Record<string, number | null>;
  order?: readonly string[];
  tone?: Record<string, string>;
}): ReactElement {
  const keys = order
    ? order.filter((k) => k in cells)
    : Object.keys(cells).sort((a, b) => a.localeCompare(b));
  const anySuppressed = keys.some((k) => cells[k] === null);

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-600">
        {title}
      </h3>
      <dl className="mt-3 grid gap-2">
        {keys.map((key) => (
          <div
            key={key}
            className="flex items-baseline justify-between gap-4 border-b border-brand-100 pb-2 last:border-0"
          >
            <dt className={cn('text-sm text-brand-700', tone?.[key])}>{key}</dt>
            <dd className="text-lg">
              <SuppressedCount value={cells[key] ?? null} />
            </dd>
          </div>
        ))}
      </dl>
      {anySuppressed ? (
        <p className="mt-3 text-xs text-brand-500">
          &mdash; marks a group withheld because too few members fall in it.
        </p>
      ) : null}
    </div>
  );
}
