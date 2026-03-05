'use client';

import { useState, useEffect } from 'react';
import { adminBff } from '@/lib/bffClient';

interface UsageMetrics {
  period: string;
  totals: { total_requests: number; ok: number; errors: number; unique_users: number };
  daily_breakdown: Array<{ day: string; action: string; count: number }>;
}

interface ReliabilityMetrics {
  period: string;
  reliability_by_action: Array<{ action: string; total: number; ok: number; errors: number; error_rate_pct: number }>;
}

export default function MetricsPage() {
  const [usage, setUsage] = useState<UsageMetrics | null>(null);
  const [reliability, setReliability] = useState<ReliabilityMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const [u, r] = await Promise.all([adminBff.getUsageMetrics(), adminBff.getReliabilityMetrics()]);
        setUsage(u as UsageMetrics);
        setReliability(r as ReliabilityMetrics);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load metrics');
      } finally { setLoading(false); }
    };
    load();
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={() => history.back()} style={{ background: 'none', border: 'none', color: '#fb923c', cursor: 'pointer', fontSize: 14 }}>← Admin</button>
        <span style={{ color: '#475569' }}>|</span>
        <span style={{ color: '#94a3b8' }}>Usage & Reliability Metrics</span>
      </nav>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 32 }}>System Metrics</h1>

        {loading && <p style={{ color: '#64748b' }}>Loading metrics…</p>}
        {error && <p style={{ color: '#f87171' }}>{error}</p>}

        {usage && (
          <>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16, color: '#fb923c' }}>Usage – Last 30 Days</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 40 }}>
              {[
                { label: 'Total Requests', value: usage.totals.total_requests, color: '#60a5fa' },
                { label: 'Successful', value: usage.totals.ok, color: '#34d399' },
                { label: 'Errors', value: usage.totals.errors, color: '#f87171' },
                { label: 'Unique Users', value: usage.totals.unique_users, color: '#a78bfa' },
              ].map(stat => (
                <div key={stat.label} style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155', textAlign: 'center' }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: stat.color }}>{stat.value}</div>
                  <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>{stat.label}</div>
                </div>
              ))}
            </div>
          </>
        )}

        {reliability && (
          <>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16, color: '#fb923c' }}>Reliability – Last 7 Days</h2>
            <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#162032' }}>
                    {['Action', 'Total', 'OK', 'Errors', 'Error Rate'].map(h => (
                      <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 13, color: '#64748b', borderBottom: '1px solid #334155' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reliability.reliability_by_action.map((row, i) => (
                    <tr key={row.action} style={{ background: i % 2 === 0 ? '#1e293b' : '#162032' }}>
                      <td style={{ padding: '10px 16px', fontSize: 13, color: '#94a3b8', fontFamily: 'monospace', borderBottom: '1px solid #1e293b' }}>{row.action}</td>
                      <td style={{ padding: '10px 16px', fontSize: 13, color: '#e2e8f0', borderBottom: '1px solid #1e293b' }}>{row.total}</td>
                      <td style={{ padding: '10px 16px', fontSize: 13, color: '#34d399', borderBottom: '1px solid #1e293b' }}>{row.ok}</td>
                      <td style={{ padding: '10px 16px', fontSize: 13, color: row.errors > 0 ? '#f87171' : '#64748b', borderBottom: '1px solid #1e293b' }}>{row.errors}</td>
                      <td style={{ padding: '10px 16px', borderBottom: '1px solid #1e293b' }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: row.error_rate_pct > 10 ? '#f87171' : '#34d399' }}>
                          {row.error_rate_pct}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {reliability.reliability_by_action.length === 0 && (
                <p style={{ textAlign: 'center', color: '#64748b', padding: 32 }}>No data in the last 7 days.</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
