/** Igbo — preview. Derives from English and overrides only reviewed keys;
 * everything else falls back to English. "Asụsụ" = language. */

import { type Dictionary, en } from './en';

export const ig: Dictionary = {
  ...en,
  language: { ...en.language, label: 'Asụsụ' },
};
