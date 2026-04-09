'use client';

import { useEffect, useMemo, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';

type Trend = { skill_id: string; skill_name: string; demand_count: number };

export default function MarketInsightsPage() {
  const { t } = useLanguage();
  const [trends, setTrends] = useState<Trend[]>([]);
  const [salaryBands, setSalaryBands] = useState<Array<{ role: string; range: string }>>([]);
  const [sourceCount, setSourceCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await studentBff.getMarketInsights();
        if (cancelled) return;
        setTrends(data.trends || []);
        setSalaryBands(data.salary_reference?.bands || []);
        setSourceCount(Number(data.source_postings_count || 0));
      } catch {
        if (cancelled) return;
        setError(t('marketInsights.loadFailed'));
        setTrends([]);
        setSalaryBands([]);
        setSourceCount(0);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [t]);

  const parseRangeMid = (range: string) => {
    const [a, b] = String(range).split('-').map((v) => Number(v.replace(/[^\d]/g, '')));
    if (!a && !b) return 0;
    if (!b) return a || 0;
    return Math.round((a + b) / 2);
  };
  const maxSalary = useMemo(() => Math.max(1, ...salaryBands.map((b) => parseRangeMid(b.range))), [salaryBands]);
  const maxDemand = useMemo(() => Math.max(1, ...trends.map((t) => t.demand_count)), [trends]);

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>{t('marketInsights.title')}</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>{t('marketInsights.subtitle')}</p>
            <p style={{ margin: '0.35rem 0 0 0', fontSize: 13, color: 'var(--gray-500)' }}>
              {t('marketInsights.dataSource')} {sourceCount} {t('marketInsights.postings')}
            </p>
          </div>
        </div>
        {error ? (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            <span className="alert-icon">⚠</span>
            <div className="alert-content">
              <div className="alert-title">{t('marketInsights.unavailable')}</div>
              <p>{error}</p>
            </div>
          </div>
        ) : null}
        <div className="grid grid-2">
          <div className="card">
            <div className="card-header"><h3 className="card-title">{t('marketInsights.trends')}</h3></div>
            <div className="card-content">
              {loading ? [1, 2, 3, 4].map((i) => (
                <div key={i} className="skeleton" style={{ height: 24, marginBottom: 10 }} />
              )) : (trends || []).map((t) => (
                <div key={t.skill_id} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>{t.skill_name}</span>
                    <strong>{t.demand_count}</strong>
                  </div>
                  <div style={{ height: 6, borderRadius: 999, background: 'var(--gray-200)' }}>
                    <div style={{ width: `${Math.max(3, Math.round((t.demand_count / maxDemand) * 100))}%`, height: '100%', borderRadius: 999, background: 'var(--hku-green)' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-header"><h3 className="card-title">{t('marketInsights.salaryReference')}</h3></div>
            <div className="card-content">
              {loading ? [1, 2, 3].map((i) => (
                <div key={i} className="skeleton" style={{ height: 20, marginBottom: 10 }} />
              )) : salaryBands.map((b) => {
                const width = Math.max(10, Math.round((parseRangeMid(b.range) / maxSalary) * 100));
                return (
                  <div key={b.role} style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                      <strong>{b.role}</strong>
                      <span>{b.range}</span>
                    </div>
                    <div style={{ height: 8, borderRadius: 999, background: 'var(--gray-200)' }}>
                      <div style={{ width: `${width}%`, height: '100%', borderRadius: 999, background: 'var(--coral)' }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
