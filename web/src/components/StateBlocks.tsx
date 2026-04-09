'use client';

import { ReactNode } from 'react';

export function PageSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 44, borderRadius: 8 }} />
      ))}
    </div>
  );
}

export function SectionSkeleton({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height, borderRadius: 12 }} />;
}

export function InlineErrorBlock({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="alert alert-error">
      <span>⚠</span>
      <div style={{ flex: 1 }}>
        <strong>{title}</strong>
        <p style={{ marginTop: '0.25rem', fontSize: '0.875rem' }}>{message}</p>
        {action ? <div style={{ marginTop: '0.75rem' }}>{action}</div> : null}
      </div>
    </div>
  );
}
