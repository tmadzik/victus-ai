'use client';

import { useTransition } from 'react';

import { LOCALE_AUTONYM, LOCALES, type Locale } from '@/i18n/config';
import { setLocaleAction } from '@/server/locale-actions';

export function LanguageSwitcher({
  current,
  label,
}: {
  current: Locale;
  label: string;
}): React.ReactElement {
  const [pending, startTransition] = useTransition();
  return (
    <select
      aria-label={label}
      value={current}
      disabled={pending}
      onChange={(e) => {
        const next = e.target.value;
        startTransition(() => {
          void setLocaleAction(next);
        });
      }}
      className="rounded-[var(--radius-control)] border border-brand-200 bg-white px-2 py-1 text-xs font-medium text-brand-800 outline-none focus:border-brand-500 disabled:opacity-60"
    >
      {LOCALES.map((l) => (
        <option key={l} value={l}>
          {LOCALE_AUTONYM[l]}
        </option>
      ))}
    </select>
  );
}
