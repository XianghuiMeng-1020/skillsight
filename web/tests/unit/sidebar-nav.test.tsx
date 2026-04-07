import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import Sidebar from '@/components/Sidebar';
import { DEMO_MODE_KEY } from '@/lib/demoMode';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/components/ApiStatus', () => ({
  default: () => <div data-testid="api-status">ok</div>,
}));

const storageShim = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();

describe('Sidebar student nav', () => {
  beforeEach(() => {
    if (!globalThis.localStorage || typeof globalThis.localStorage.clear !== 'function') {
      Object.defineProperty(globalThis, 'localStorage', {
        value: storageShim,
        configurable: true,
      });
    }
    localStorage.clear();
    localStorage.setItem('user', JSON.stringify({ role: 'student', name: 'Demo', avatar: 'D' }));
    if (!window.matchMedia) {
      // Minimal matchMedia mock for sidebar responsive hook
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      window.matchMedia = () => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      });
    }
  });

  it('shows Sample Cases but hides Change Log for students', async () => {
    render(<Sidebar />);
    expect(await screen.findByText('nav.sampleCases')).toBeTruthy();
    expect(screen.queryByText('changelog.navLabel')).toBeNull();
  });

  it('shows demo safety hint when demo mode is enabled', async () => {
    localStorage.setItem(DEMO_MODE_KEY, '1');
    render(<Sidebar />);

    expect(await screen.findByText('jobs.demoModeOn')).toBeTruthy();
    expect(screen.getByText((text) => text.includes('demo.noBackendWrite'))).toBeTruthy();
  });
});
