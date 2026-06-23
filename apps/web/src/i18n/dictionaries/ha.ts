/** Hausa — preview. Derives from English and overrides only reviewed keys;
 * everything else falls back to English. "Harshe" = language. */

import { type Dictionary, en } from './en';

export const ha: Dictionary = {
  ...en,
  language: { ...en.language, label: 'Harshe' },
};
