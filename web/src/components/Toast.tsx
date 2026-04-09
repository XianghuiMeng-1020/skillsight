'use client';

import { useEffect, useState, useRef, createContext, useContext, ReactNode, useCallback } from 'react';

interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration?: number;
}

interface ToastContextType {
  toasts: Toast[];
  addToast: (type: Toast['type'], message: string, duration?: number) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const addToast = useCallback((type: Toast['type'], message: string, duration = 4000) => {
    const id =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2);
    setToasts(prev => {
      const next = [...prev, { id, type, message, duration }];
      // Keep toast stack bounded so the viewport does not get flooded.
      return next.length > 5 ? next.slice(next.length - 5) : next;
    });
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}

function ToastContainer({ toasts, removeToast }: { toasts: Toast[]; removeToast: (id: string) => void }) {
  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: 'fixed',
      bottom: '1.5rem',
      right: '1.5rem',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: '0.75rem',
      maxWidth: '400px',
    }}
    role="status"
    aria-live="polite"
    >
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const [isLeaving, setIsLeaving] = useState(false);
  const closeOnceRef = useRef(false);

  const closeWithAnimation = useCallback(() => {
    if (closeOnceRef.current) return;
    closeOnceRef.current = true;
    setIsLeaving(true);
    window.setTimeout(onClose, 200);
  }, [onClose]);

  useEffect(() => {
    if (toast.duration && toast.duration > 0) {
      const delay = Math.max(0, toast.duration - 200);
      const timer = window.setTimeout(closeWithAnimation, delay);
      return () => clearTimeout(timer);
    }
  }, [toast.duration, closeWithAnimation]);

  const colors = {
    success: { bg: 'var(--success-light)', border: 'var(--success)', icon: '✓', color: 'var(--gray-900)' },
    error: { bg: 'var(--error-light)', border: 'var(--error)', icon: '✕', color: 'var(--gray-900)' },
    warning: { bg: 'var(--warning-light)', border: 'var(--warning)', icon: '⚠', color: 'var(--gray-900)' },
    info: { bg: 'var(--info-light)', border: 'var(--info)', icon: 'ℹ', color: 'var(--gray-900)' },
  };

  const style = colors[toast.type];

  return (
    <div
      style={{
        background: style.bg,
        border: `1px solid ${style.border}`,
        color: style.color,
        padding: '1rem 1.25rem',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        animation: isLeaving ? 'fadeOut 0.2s ease forwards' : 'slideIn 0.2s ease forwards',
      }}
    >
      <span style={{ fontSize: '1.25rem', flexShrink: 0 }}>{style.icon}</span>
      <span style={{ flex: 1, fontSize: '0.875rem', fontWeight: 500 }}>{toast.message}</span>
      <button
        onClick={closeWithAnimation}
        aria-label="Close notification"
        style={{
          background: 'transparent',
          border: 'none',
          color: style.color,
          cursor: 'pointer',
          padding: '0.25rem',
          opacity: 0.7,
          fontSize: '1rem',
        }}
      >
        ✕
      </button>
    </div>
  );
}

// API helper with toast notifications and network retry
const API_RETRY_ATTEMPTS = 3;
const API_RETRY_DELAYS = [2000, 4000];

export async function apiCall<T>(
  url: string,
  options?: RequestInit,
  toast?: ToastContextType
): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt < API_RETRY_ATTEMPTS; attempt++) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        const message = error.detail || `Error: ${response.status}`;
        toast?.addToast('error', message);
        throw new Error(message);
      }

      return response.json();
    } catch (error) {
      lastError = error;
      const isNetworkError =
        error instanceof TypeError &&
        (error.message === 'Failed to fetch' || error.message?.includes('fetch'));
      if (!isNetworkError || attempt === API_RETRY_ATTEMPTS - 1) {
        if (error instanceof Error && !error.message.includes('Error:')) {
          toast?.addToast('error', 'Network error. Server may be waking up, please try again.');
        }
        throw error;
      }
      const delay = API_RETRY_DELAYS[attempt] ?? 4000;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw lastError;
}
