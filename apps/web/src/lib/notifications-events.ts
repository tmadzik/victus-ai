/**
 * Dependency-free cross-component signal for notification state changes.
 *
 * When the `/notifications` page marks something read, it emits this event so
 * the header bell can refetch its unread count immediately — without waiting
 * for the next poll tick. Both live in different parts of the tree with no
 * shared React context, so a window CustomEvent is the lightest correct
 * coupling.
 *
 * All functions are SSR-safe: they no-op when `window` is undefined.
 */

const EVENT_NAME = 'victus:notifications-updated';

export function emitNotificationsUpdated(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(EVENT_NAME));
}

/**
 * Subscribe to notification-updated events. Returns an unsubscribe function;
 * call it on cleanup. No-op (returns a noop unsubscribe) during SSR.
 */
export function onNotificationsUpdated(callback: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const handler = (): void => callback();
  window.addEventListener(EVENT_NAME, handler);
  return () => window.removeEventListener(EVENT_NAME, handler);
}
