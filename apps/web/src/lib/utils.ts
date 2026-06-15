export { cn } from '@victus/ui';

export function formatDate(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  return new Intl.DateTimeFormat('en-ZA', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}
