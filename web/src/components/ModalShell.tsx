'use client';

import {
  useCallback,
  useEffect,
  useRef,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from 'react';

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface ModalShellProps {
  open: boolean;
  onClose: () => void;
  /** Element id for `aria-labelledby` (e.g. modal title heading). */
  titleId?: string;
  children: ReactNode;
  className?: string;
  overlayClassName?: string;
  modalStyle?: CSSProperties;
}

/**
 * Shared modal: `.modal-overlay` + `.modal` from globals.css (scale open animation).
 * Focus moves into the dialog on open, Tab cycles within, Escape closes, focus restores on close.
 */
export function ModalShell({
  open,
  onClose,
  titleId,
  children,
  className = '',
  overlayClassName = '',
  modalStyle,
}: ModalShellProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const prevActiveRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    prevActiveRef.current = document.activeElement as HTMLElement | null;
    const root = dialogRef.current;
    if (root) {
      const first = root.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      (first ?? root).focus();
    }
    return () => {
      prevActiveRef.current?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const onDialogKeyDown = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab' || !dialogRef.current) return;
    const nodes = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((el) => !el.closest('[aria-hidden="true"]'));
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, []);

  if (!open) return null;

  return (
    <div
      className={`modal-overlay open ${overlayClassName}`.trim()}
      role="presentation"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`modal ${className}`.trim()}
        style={modalStyle}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onDialogKeyDown}
      >
        {children}
      </div>
    </div>
  );
}
