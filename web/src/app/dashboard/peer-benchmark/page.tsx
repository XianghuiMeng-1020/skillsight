'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';
import { DEMO_PEER_BENCHMARK } from '@/lib/demoDataset';

type Item = { skill_id: string; level: number; percentile: number };

const LEVEL_LABELS: Record<number, string> = { 0: 'Not demonstrated', 1: 'Mentioned', 2: 'Applied', 3: 'Demonstrated', 4: 'Proficient', 5: 'Expert' };

export default function PeerBenchmarkPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDemo, setIsDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await studentBff.getPeerBenchmark();
        if (!cancelled) {
          if ((data.items || []).length === 0) {
            setItems(DEMO_PEER_BENCHMARK);
            setIsDemo(true);
          } else {
            setItems(data.items);
            setIsDemo(false);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setItems(DEMO_PEER_BENCHMARK);
          setIsDemo(true);
          if (e instanceof Error && !e.message.includes('401')) {
            setError('Could not load live data — showing demo benchmark.');
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const normalizeSkill = (skillId: string) =>
    skillId.replace(/^HKU\.SKILL\./i, '').replace(/\.v\d+$/i, '').replace(/_/g, ' ');

  const barColor = (pct: number) => {
    if (pct >= 70) return 'var(--hku-green)';
    if (pct >= 40) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>Peer Benchmarking</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>
              Compare your verified skill levels against anonymous peers.
              {isDemo && (
                <span style={{ marginLeft: 8, fontSize: 12, background: 'var(--warning-bg, #fef3c7)', color: '#92400e', padding: '2px 8px', borderRadius: 4 }}>
                  Sample data — upload a document and complete assessments to see your real ranking
                </span>
              )}
            </p>
          </div>
        </div>

        {error && (
          <div className="card" style={{ marginBottom: '1rem', borderLeft: '4px solid var(--warning-color, #f59e0b)' }}>
            <div className="card-content" style={{ padding: '0.75rem 1rem', color: 'var(--gray-600)' }}>{error}</div>
          </div>
        )}

        <div className="card">
          <div className="card-content">
            {loading ? (
              [1, 2, 3, 4].map((i) => (
                <div key={i} className="skeleton" style={{ height: 44, marginBottom: 14, borderRadius: 8 }} />
              ))
            ) : items.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--gray-500)' }}>
                <p style={{ fontSize: 32, margin: 0 }}>📊</p>
                <p style={{ margin: '0.5rem 0 0' }}>No benchmark data yet.</p>
                <p style={{ fontSize: 13, margin: '0.25rem 0 0' }}>Upload a document and run skill assessment to compare with peers.</p>
              </div>
            ) : (
              <>
                <p style={{ margin: '0 0 1rem', fontSize: 13, color: 'var(--gray-500)' }}>
                  {items.length} skills assessed · Percentile shows your standing among all peers
                </p>
                {items.map((it) => {
                  const topPct = Math.max(0, 100 - Math.round(it.percentile));
                  const levelLabel = LEVEL_LABELS[it.level] ?? `Level ${it.level}`;
                  return (
                    <div key={it.skill_id} style={{ marginBottom: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, alignItems: 'baseline' }}>
                        <span style={{ textTransform: 'capitalize', fontWeight: 500 }}>{normalizeSkill(it.skill_id)}</span>
                        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                          <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>{levelLabel}</span>
                          <strong style={{ color: barColor(it.percentile) }}>Top {topPct}%</strong>
                        </div>
                      </div>
                      <div style={{ height: 10, borderRadius: 999, background: 'var(--gray-200)' }}>
                        <div
                          style={{
                            height: '100%',
                            width: `${Math.max(3, Math.min(100, it.percentile))}%`,
                            borderRadius: 999,
                            background: barColor(it.percentile),
                            transition: 'width 0.6s ease',
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
