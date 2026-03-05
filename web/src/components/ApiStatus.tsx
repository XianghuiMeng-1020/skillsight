'use client';

import { useEffect, useState } from 'react';

interface ApiStatusProps {
  showLabel?: boolean;
}

export default function ApiStatus({ showLabel = true }: ApiStatusProps) {
  const [status, setStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');

  useEffect(() => {
    const checkApi = async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/health`, {
          method: 'GET',
          signal: AbortSignal.timeout(3000),
        });
        setStatus(response.ok ? 'connected' : 'disconnected');
      } catch {
        setStatus('disconnected');
      }
    };

    checkApi();
    const interval = setInterval(checkApi, 30000); // Check every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const colors = {
    checking: { bg: 'var(--gray-400)', pulse: true },
    connected: { bg: 'var(--success)', pulse: false },
    disconnected: { bg: 'var(--error)', pulse: true },
  };

  const labels = {
    checking: 'Checking...',
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
        color: 'var(--gray-500)',
      }}
      title={status === 'disconnected' ? 'Backend server is not running. Start it with: PYTHONPATH=. python -m uvicorn backend.app.main:app --port 8001' : undefined}
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
