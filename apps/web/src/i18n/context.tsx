'use client';

import { createContext, useContext } from 'react';

import { DEFAULT_LOCALE, formatLocale, type Locale } from '@/i18n/config';
import { type Dictionary, en } from '@/i18n/dictionaries/en';

// Carries the resolved dictionary + active locale to client components (wizards,
// cards) that can't call the server-only getDictionary()/getLocale(). Defaults
// to English so a component rendered outside the provider still works.
const DictionaryContext = createContext<Dictionary>(en);
const LocaleContext = createContext<Locale>(DEFAULT_LOCALE);

export function DictionaryProvider({
  dict,
  locale,
  children,
}: {
  dict: Dictionary;
  locale: Locale;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <DictionaryContext.Provider value={dict}>
      <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>
    </DictionaryContext.Provider>
  );
}

export function useDictionary(): Dictionary {
  return useContext(DictionaryContext);
}

export function useLocale(): Locale {
  return useContext(LocaleContext);
}

/** BCP-47 tag for date/number formatting, following the active locale's pilot
 * country (en-ZW / en-NG; en-GB for neutral English). */
export function useFormatLocale(): string {
  return formatLocale(useContext(LocaleContext));
}
