/** Locale configuration — shared by server (dictionary resolution) and client
 * (the language switcher). No 'server-only' here so the client may import it. */

// en + the Zimbabwe pilot (sn/nd) + the Nigeria pilot (yo/ig/ha/pcm).
export const LOCALES = ['en', 'sn', 'nd', 'yo', 'ig', 'ha', 'pcm'] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'en';
export const LOCALE_COOKIE = 'victus_locale';

/** Autonyms (each language's own name) — never translated. */
export const LOCALE_AUTONYM: Record<Locale, string> = {
  en: 'English',
  sn: 'ChiShona',
  nd: 'IsiNdebele',
  yo: 'Yorùbá',
  ig: 'Igbo',
  ha: 'Hausa',
  pcm: 'Naijá',
};

/**
 * BCP-47 tag used for date/number formatting. Follows the participant's pilot
 * country: the Zimbabwe languages format as en-ZW, the Nigeria languages as
 * en-NG. Plain English stays region-neutral (en-GB — day-month-year, no country
 * claim) since it is shared across both pilots. (NOT en-ZA — this is a Zimbabwe
 * and Nigeria project.)
 */
const FORMAT_LOCALE: Record<Locale, string> = {
  en: 'en-GB',
  sn: 'en-ZW',
  nd: 'en-ZW',
  yo: 'en-NG',
  ig: 'en-NG',
  ha: 'en-NG',
  pcm: 'en-NG',
};

export function formatLocale(locale: Locale): string {
  return FORMAT_LOCALE[locale] ?? 'en-GB';
}

/**
 * The one phrase vetted across the Zimbabwe languages (the same prompt the
 * WhatsApp rail uses to open the conversation). Every non-English locale falls
 * back to English until a native + clinical review supplies the translations.
 */
export const CHOOSE_LANGUAGE_PROMPT = 'Choose a language · Sarudza mutauro · Khetha ulimi';

export function isLocale(value: string | undefined | null): value is Locale {
  return (LOCALES as readonly string[]).includes(value ?? '');
}
