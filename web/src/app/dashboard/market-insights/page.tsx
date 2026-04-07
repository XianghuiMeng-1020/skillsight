'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';

type Trend = { skill_id: string; skill_name: string; demand_count: number };

export default function MarketInsightsPage() {
  const [trends, setTrends] = useState<Trend[]>([]);
  const [salaryBands, setSalaryBands] = useState<Array<{ role: string; range: string }>>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await studentBff.getMarketInsights();
        if (cancelled) return;
        setTrends(data.trends || []);
        setSalaryBands(data.salary_reference?.bands || []);
      } catch {
        setTrends([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>HK Job Market Insights</h1>
          <p>Live demand signals from role requirements and public job snapshots.</p>
        </div>
        <div className="grid grid-2">
          <div className="card">
            <div className="card-header"><h3 className="card-title">Skill Demand Trends</h3></div>
            <div className="card-content">
              {(trends || []).map((t) => (
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
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {salaryBands.map((b) => (
                  <li key={b.role} style={{ marginBottom: 6 }}>
                    <strong>{b.role}</strong>: {b.range}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
