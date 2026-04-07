'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';

type Item = { skill_id: string; level: number; percentile: number };

export default function PeerBenchmarkPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await studentBff.getPeerBenchmark();
        if (!cancelled) setItems(data.items || []);
      } catch {
        if (!cancelled) setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const normalizeSkill = (skillId: string) =>
    skillId.replace(/^HKU\.SKILL\./i, '').replace(/\.v\d+$/i, '').replace(/_/g, ' ');

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>Peer Benchmarking</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>Compare your verified skill levels against anonymous peers.</p>
          </div>
        </div>
        <div className="card">
          <div className="card-content">
            {loading ? [1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton" style={{ height: 20, marginBottom: 10 }} />
            )) : items.length === 0 ? (
              <p>No benchmark data yet.</p>
            ) : (
              items.map((it) => (
                <div key={it.skill_id} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ textTransform: 'capitalize' }}>{normalizeSkill(it.skill_id)}</span>
                    <strong>Top {Math.max(0, 100 - Math.round(it.percentile))}%</strong>
                  </div>
                  <div style={{ height: 8, borderRadius: 999, background: 'var(--gray-200)' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${Math.max(3, Math.min(100, it.percentile))}%`,
                        borderRadius: 999,
                        background: 'var(--hku-green)',
                      }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
