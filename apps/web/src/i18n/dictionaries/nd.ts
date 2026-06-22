/** IsiNdebele (Ndebele) — preview. Derives from English and overrides only the
 * keys with a reviewed translation; everything else falls back to English. The
 * single vetted term ("ulimi" = language) matches the WhatsApp rail's wording. */

import { type Dictionary, en } from './en';

export const nd: Dictionary = {
  ...en,
  language: { ...en.language, label: 'Ulimi' },
};
