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
 * The one phrase vetted across the Zimbabwe languages (the same prompt the
 * WhatsApp rail uses to open the conversation). Every non-English locale falls
 * back to English until a native + clinical review supplies the translations.
 */
export const CHOOSE_LANGUAGE_PROMPT = 'Choose a language · Sarudza mutauro · Khetha ulimi';

export function isLocale(value: string | undefined | null): value is Locale {
  return (LOCALES as readonly string[]).includes(value ?? '');
}
