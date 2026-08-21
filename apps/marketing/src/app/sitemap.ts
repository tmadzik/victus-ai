import type { MetadataRoute } from 'next';

import { SITE_URL } from '@/lib/site';

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: SITE_URL, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE_URL}/platform`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/for/clinicians`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/for/funders`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/for/kiosk`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE_URL}/legal`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${SITE_URL}/privacy`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${SITE_URL}/paia`, changeFrequency: 'yearly', priority: 0.3 },
  ];
}
