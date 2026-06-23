'use client';

import { createContext, useContext } from 'react';

import { type Dictionary, en } from '@/i18n/dictionaries/en';

// Carries the resolved dictionary to client components (wizards) that can't call
// the server-only getDictionary(). Defaults to English so a component rendered
// outside the provider still works.
const DictionaryContext = createContext<Dictionary>(en);

export function DictionaryProvider({
  dict,
  children,
}: {
  dict: Dictionary;
  children: React.ReactNode;
}): React.ReactElement {
  return <DictionaryContext.Provider value={dict}>{children}</DictionaryContext.Provider>;
}

export function useDictionary(): Dictionary {
  return useContext(DictionaryContext);
}
