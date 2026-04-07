'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';

type Trend = { skill_id: string; skill_name: string; demand_count: number };

export default function MarketInsightsPage() {
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
        setError('Failed to load market insights.');
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
  }, []);

  const parseRangeMid = (range: string) => {
    const [a, b] = String(range).split('-').map((v) => Number(v.replace(/[^\d]/g, '')));
    if (!a && !b) return 0;
    if (!b) return a || 0;
    return Math.round((a + b) / 2);
  };
  const maxSalary = Math.max(1, ...salaryBands.map((b) => parseRangeMid(b.range)));

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>HK Job Market Insights</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>Live demand signals from role requirements and public job snapshots.</p>
            <p style={{ margin: '0.35rem 0 0 0', fontSize: 13, color: 'var(--gray-500)' }}>
              Data source: {sourceCount} job postings
            </p>
          </div>
        </div>
        {error ? (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            <span className="alert-icon">⚠</span>
            <div className="alert-content">
              <div className="alert-title">Market insights unavailable</div>
              <p>{error}</p>
            </div>
          </div>
        ) : null}
        <div className="grid grid-2">
          <div className="card">
            <div className="card-header"><h3 className="card-title">Skill Demand Trends</h3></div>
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
                    <div style={{ width: `${Math.min(100, t.demand_count * 8)}%`, height: '100%', borderRadius: 999, background: 'var(--hku-green)' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-header"><h3 className="card-title">Salary Reference (HKD)</h3></div>
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
