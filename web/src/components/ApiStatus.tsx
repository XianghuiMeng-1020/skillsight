'use client';

import { useEffect, useState, useRef } from 'react';

interface ApiStatusProps {
  showLabel?: boolean;
}

type Status = 'checking' | 'waking' | 'connected' | 'disconnected';

export default function ApiStatus({ showLabel = true }: ApiStatusProps) {
  const [status, setStatus] = useState<Status>('checking');
  const retryCount = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const checkApi = async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/health`, {
          method: 'GET',
          signal: AbortSignal.timeout(8000),
        });
        if (!cancelled) {
          setStatus(response.ok ? 'connected' : 'disconnected');
          retryCount.current = 0;
        }
      } catch {
        if (cancelled) return;
        retryCount.current += 1;
        if (retryCount.current <= 6) {
          setStatus('waking');
          timer = setTimeout(checkApi, 5000);
          return;
        }
        setStatus('disconnected');
      }
    };

    checkApi();
    const interval = setInterval(() => {
      if (retryCount.current === 0) checkApi();
    }, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
      if (timer) clearTimeout(timer);
    };
  }, []);

  const colors: Record<Status, { bg: string; pulse: boolean }> = {
    checking: { bg: 'var(--gray-400)', pulse: true },
    waking: { bg: '#F59E0B', pulse: true },
    connected: { bg: 'var(--success)', pulse: false },
    disconnected: { bg: 'var(--error)', pulse: true },
  };

  const labels: Record<Status, string> = {
    checking: 'Checking...',
    waking: 'Server waking up...',
    connected: 'API Connected',
    disconnected: 'API Offline',
  };

  const style = colors[status];

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontSize: '0.75rem',
        color: status === 'waking' ? '#F59E0B' : 'var(--gray-500)',
      }}
      title={
        status === 'waking'
          ? 'Free-tier server is cold-starting. This usually takes 30-60 seconds.'
          : status === 'disconnected'
            ? 'Backend server is not running.'
            : undefined
      }
    >
      <div
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: style.bg,
          animation: style.pulse ? 'pulse 2s ease-in-out infinite' : undefined,
        }}
      />
      {showLabel && <span>{labels[status]}</span>}
    </div>
  );
}
