import 'server-only';

import { cookies } from 'next/headers';

import { DEFAULT_LOCALE, isLocale, LOCALE_COOKIE, type Locale } from './config';
import { type Dictionary, en } from './dictionaries/en';
import { ha } from './dictionaries/ha';
import { ig } from './dictionaries/ig';
import { nd } from './dictionaries/nd';
import { pcm } from './dictionaries/pcm';
import { sn } from './dictionaries/sn';
import { yo } from './dictionaries/yo';

const DICTIONARIES: Record<Locale, Dictionary> = { en, sn, nd, yo, ig, ha, pcm };

/** Resolve the active locale from the cookie (server components only). */
export async function getLocale(): Promise<Locale> {
  const value = (await cookies()).get(LOCALE_COOKIE)?.value;
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

export function getDictionary(locale: Locale): Dictionary {
  return DICTIONARIES[locale];
}

/** Convenience: the active locale and its dictionary in one call. */
export async function getI18n(): Promise<{ locale: Locale; dict: Dictionary }> {
  const locale = await getLocale();
  return { locale, dict: getDictionary(locale) };
}

export type { Dictionary, Locale };
