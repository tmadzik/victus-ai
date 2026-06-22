'use server';

import { revalidatePath } from 'next/cache';
import { cookies } from 'next/headers';

import { isLocale, LOCALE_COOKIE } from '@/i18n/config';

const ONE_YEAR = 60 * 60 * 24 * 365;

/** Persist the chosen locale and re-render the app under the new language. */
export async function setLocaleAction(locale: string): Promise<void> {
  if (!isLocale(locale)) return;
  (await cookies()).set(LOCALE_COOKIE, locale, {
    path: '/',
    maxAge: ONE_YEAR,
    sameSite: 'lax',
  });
  revalidatePath('/', 'layout');
}
