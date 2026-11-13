/**
 * Full page load. Used after signing in or out: the app router may hold pages
 * prefetched under the old session (e.g. /coach as a redirect to /login).
 */
export function loadPage(url: string): void {
  window.location.assign(url);
}
