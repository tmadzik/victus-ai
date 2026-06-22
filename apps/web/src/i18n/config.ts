/** Locale configuration — shared by server (dictionary resolution) and client
 * (the language switcher). No 'server-only' here so the client may import it. */

export const LOCALES = ['en', 'sn', 'nd'] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'en';
export const LOCALE_COOKIE = 'victus_locale';

/** Autonyms (each language's own name) — never translated. */
export const LOCALE_AUTONYM: Record<Locale, string> = {
  en: 'English',
  sn: 'ChiShona',
  nd: 'IsiNdebele',
};

/**
 * The one phrase vetted across all three languages (it is the same prompt the
 * WhatsApp rail uses to open the conversation). Everything else in sn/nd falls
 * back to English until a native + clinical review supplies the translations.
 */
export const CHOOSE_LANGUAGE_PROMPT = 'Choose a language · Sarudza mutauro · Khetha ulimi';

export function isLocale(value: string | undefined | null): value is Locale {
  return value === 'en' || value === 'sn' || value === 'nd';
}
