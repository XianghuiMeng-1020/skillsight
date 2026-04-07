'use client';

import type { CSSProperties } from 'react';
import { useLanguage } from '@/lib/contexts';

interface DemoSafeHintProps {
  className?: string;
  style?: CSSProperties;
  withIcon?: boolean;
  severity?: 'muted' | 'warn';
  display?: 'inline' | 'block';
  size?: 'default' | 'compact';
}

export default function DemoSafeHint({
  className,
  style,
  withIcon = true,
  severity = 'muted',
  display = 'inline',
  size = 'default',
}: DemoSafeHintProps) {
  const { t } = useLanguage();
  const isWarn = severity === 'warn';
  const isCompact = size === 'compact';

  return (
    <span
      className={className}
      style={{
        display: display === 'block' ? 'flex' : 'inline-flex',
        alignItems: 'center',
        width: display === 'block' ? 'fit-content' : undefined,
        fontSize: isCompact ? '0.6875rem' : '0.75rem',
        lineHeight: 1.2,
        color: isWarn ? 'var(--warning-dark, #92400e)' : 'var(--gray-600)',
        background: isWarn ? 'var(--warning-light, #fef3c7)' : 'transparent',
        border: isWarn ? '1px solid var(--warning, #f59e0b)' : 'none',
        borderRadius: isWarn ? '999px' : 0,
        padding: isWarn ? (isCompact ? '0.125rem 0.4rem' : '0.2rem 0.55rem') : 0,
        fontWeight: isWarn ? 500 : 400,
        ...style,
      }}
    >
      {withIcon ? `🧪 ${t('demo.noBackendWrite')}` : t('demo.noBackendWrite')}
    </span>
  );
}
