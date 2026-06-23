/** Yorùbá — preview. Derives from English and overrides only reviewed keys;
 * everything else falls back to English (clinical copy must not be machine-
 * translated without review). "Èdè" = language. */

import { type Dictionary, en } from './en';

export const yo: Dictionary = {
  ...en,
  language: { ...en.language, label: 'Èdè' },
};
