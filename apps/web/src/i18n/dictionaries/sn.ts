/** ChiShona (Shona) — preview. Derives from English and overrides only the keys
 * with a reviewed translation; everything else falls back to English. The single
 * vetted term ("mutauro" = language) matches the WhatsApp rail's wording. */

import { type Dictionary, en } from './en';

export const sn: Dictionary = {
  ...en,
  language: { ...en.language, label: 'Mutauro' },
};
