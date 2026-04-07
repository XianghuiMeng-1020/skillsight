import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import DemoSafeHint from '@/components/DemoSafeHint';

vi.mock('@/lib/contexts', () => ({
  useLanguage: () => ({
    t: (key: string) => (key === 'demo.noBackendWrite' ? 'Demo-only：不会写入真实后端' : key),
  }),
}));

describe('DemoSafeHint', () => {
  it('renders default muted inline hint with icon', () => {
    const { container } = render(<DemoSafeHint />);
    const el = container.firstElementChild as HTMLElement;

    expect(el.textContent).toContain('🧪 Demo-only：不会写入真实后端');
    const style = el.getAttribute('style') || '';
    expect(style).toContain('display: inline-flex');
    expect(style).toContain('font-size: 0.75rem');
    expect(style).toContain('color: var(--gray-600)');
  });

  it('renders warn compact pill style', () => {
    const { container } = render(<DemoSafeHint severity="warn" size="compact" />);
    const el = container.firstElementChild as HTMLElement;

    const style = el.getAttribute('style') || '';
    expect(style).toContain('font-size: 0.6875rem');
    expect(style).toContain('border: 1px solid var(--warning, #f59e0b)');
    expect(style).toContain('border-radius: 999px');
    expect(style).toContain('padding: 0.125rem 0.4rem');
  });

  it('supports block display and hides icon when configured', () => {
    const { container } = render(<DemoSafeHint display="block" withIcon={false} />);
    const el = container.firstElementChild as HTMLElement;

    expect(el.textContent).toBe('Demo-only：不会写入真实后端');
    expect(el.textContent).not.toContain('🧪');
    const style = el.getAttribute('style') || '';
    expect(style).toContain('display: flex');
    expect(style).toContain('width: fit-content');
  });
});
