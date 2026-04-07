'use client';

import type { ButtonHTMLAttributes, PropsWithChildren } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function UIButton({ variant = 'primary', className = '', children, ...props }: PropsWithChildren<ButtonProps>) {
  const v = variant === 'primary' ? 'btn-primary' : variant === 'secondary' ? 'btn-secondary' : 'btn-ghost';
  return (
    <button {...props} className={`btn ${v} ${className}`.trim()}>
      {children}
    </button>
  );
}
