'use client';

import type { PropsWithChildren } from 'react';

export function UICard({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`card ${className}`.trim()}>{children}</section>;
}

export function UICardHeader({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <header className={`card-header ${className}`.trim()}>{children}</header>;
}

export function UICardContent({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <div className={`card-content ${className}`.trim()}>{children}</div>;
}
