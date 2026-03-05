'use client';

import { useEffect, useState, createContext, useContext, ReactNode, useCallback } from 'react';

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
    const id = Math.random().toString(36).slice(2);
    setToasts(prev => [...prev, { id, type, message, duration }]);
    
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration);
    }
  }, [removeToast]);

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
    }}>
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const [isLeaving, setIsLeaving] = useState(false);

  useEffect(() => {
    if (toast.duration && toast.duration > 0) {
      const timer = setTimeout(() => {
        setIsLeaving(true);
        setTimeout(onClose, 200);
      }, toast.duration - 200);
      return () => clearTimeout(timer);
    }
  }, [toast.duration, onClose]);

  const colors = {
    success: { bg: '#dcfce7', border: '#86efac', icon: '✓', color: '#166534' },
    error: { bg: '#fee2e2', border: '#fca5a5', icon: '✕', color: '#991b1b' },
    warning: { bg: '#fef3c7', border: '#fcd34d', icon: '⚠', color: '#92400e' },
    info: { bg: '#dbeafe', border: '#93c5fd', icon: 'ℹ', color: '#1e40af' },
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
        onClick={() => { setIsLeaving(true); setTimeout(onClose, 200); }}
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

// API helper with toast notifications
export async function apiCall<T>(
  url: string,
  options?: RequestInit,
  toast?: ToastContextType
): Promise<T> {
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
    if (error instanceof Error && !error.message.includes('Error:')) {
      toast?.addToast('error', 'Network error. Please check your connection.');
    }
    throw error;
  }
}
