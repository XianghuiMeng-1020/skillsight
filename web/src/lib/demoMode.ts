'use client';

export const DEMO_MODE_KEY = 'skillsight-demo-mode-v1';
export const DEMO_MODE_EVENT = 'skillsight-demo-mode-changed';

export function readDemoMode(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return localStorage.getItem(DEMO_MODE_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeDemoMode(enabled: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    if (enabled) localStorage.setItem(DEMO_MODE_KEY, '1');
    else localStorage.removeItem(DEMO_MODE_KEY);
    window.dispatchEvent(new CustomEvent(DEMO_MODE_EVENT, { detail: { enabled } }));
  } catch {
    // noop
  }
}

export function isDemoQuery(searchValue: string | null | undefined): boolean {
  return searchValue === '1';
}

export function withDemoQuery(path: string, enabled: boolean): string {
  if (!enabled) return path;
  const [baseWithQuery, hash = ''] = path.split('#', 2);
  const [basePath, query = ''] = baseWithQuery.split('?', 2);
  const pairs = query
    .split('&')
    .map((v) => v.trim())
    .filter(Boolean)
    .filter((v) => !v.startsWith('demo='));
  pairs.push('demo=1');
  const merged = `${basePath}?${pairs.join('&')}`;
  return hash ? `${merged}#${hash}` : merged;
}
