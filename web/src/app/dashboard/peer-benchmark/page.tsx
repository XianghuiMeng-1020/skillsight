'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { InlineErrorBlock, PageSkeleton } from '@/components/StateBlocks';
import { studentBff } from '@/lib/bffClient';
import { DEMO_PEER_BENCHMARK } from '@/lib/demoDataset';
import { useLanguage } from '@/lib/contexts';

type Item = { skill_id: string; level: number; percentile: number | null };

const LEVEL_LABELS: Record<number, string> = { 0: 'Not demonstrated', 1: 'Mentioned', 2: 'Applied', 3: 'Demonstrated', 4: 'Proficient', 5: 'Expert' };

export default function PeerBenchmarkPage() {
  const { t } = useLanguage();
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
            setError(t('peerBenchmark.loadFallback'));
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
    if (pct >= 40) return 'var(--warning)';
    return 'var(--error)';
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>{t('peerBenchmark.title')}</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>
              {t('peerBenchmark.subtitle')}
              {isDemo && (
                <span style={{ marginLeft: 8, fontSize: 12, background: 'var(--warning-light)', color: 'var(--warning)', padding: '2px 8px', borderRadius: 4 }}>
                  {t('peerBenchmark.demoHint')}
                </span>
              )}
            </p>
          </div>
        </div>

        {error && <InlineErrorBlock title={t('common.error')} message={error} />}

        <div className="card">
          <div className="card-content">
            {loading ? (
              <PageSkeleton rows={4} />
            ) : items.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--gray-500)' }}>
                <p style={{ fontSize: 32, margin: 0 }}>📊</p>
                <p style={{ margin: '0.5rem 0 0' }}>{t('peerBenchmark.emptyTitle')}</p>
                <p style={{ fontSize: 13, margin: '0.25rem 0 0' }}>{t('peerBenchmark.emptyDesc')}</p>
              </div>
            ) : (
              <>
                <p style={{ margin: '0 0 1rem', fontSize: 13, color: 'var(--gray-500)' }}>
                  {t('peerBenchmark.countPrefix')} {items.length} {t('peerBenchmark.countSuffix')}
                </p>
                {items.map((it) => {
                  const percentile = typeof it.percentile === 'number' ? it.percentile : null;
                  const topPct = percentile === null ? null : Math.max(0, 100 - Math.round(percentile));
                  const levelLabel = LEVEL_LABELS[it.level] ?? `Level ${it.level}`;
                  return (
                    <div key={it.skill_id} style={{ marginBottom: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, alignItems: 'baseline' }}>
                        <span style={{ textTransform: 'capitalize', fontWeight: 500 }}>{normalizeSkill(it.skill_id)}</span>
                        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                          <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>{levelLabel}</span>
                          <strong style={{ color: percentile === null ? 'var(--gray-500)' : barColor(percentile) }}>
                            {topPct === null ? t('peerBenchmark.na') : `${t('peerBenchmark.topPrefix')} ${topPct}%`}
                          </strong>
                        </div>
                      </div>
                      <div style={{ height: 10, borderRadius: 999, background: 'var(--gray-200)' }}>
                        <div
                          style={{
                            height: '100%',
                            width: `${Math.max(3, Math.min(100, percentile ?? 3))}%`,
                            borderRadius: 999,
                            background: percentile === null ? 'var(--gray-300)' : barColor(percentile),
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
