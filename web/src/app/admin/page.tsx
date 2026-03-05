'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { adminBff, devLogin, getToken, BffRole } from '@/lib/bffClient';

interface HealthData {
  status: string;
  stats?: {
    documents: number;
    chunks: number;
    active_consents: number;
    open_review_tickets: number;
    registered_users: number;
  };
}

export default function AdminDashboard() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loggedIn, setLoggedIn] = useState(false);
  const [loginId, setLoginId] = useState('admin_demo');

  const handleLogin = async () => {
    try {
      await devLogin({ subject_id: loginId, role: 'admin' as BffRole });
      setLoggedIn(true);
      loadHealth();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Login failed'); }
  };

  const loadHealth = async () => {
    setLoading(true);
    try {
      const data = await adminBff.getHealth();
      setHealth(data as HealthData);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load health data');
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (getToken()) { setLoggedIn(true); loadHealth(); }
    else setLoading(false);
  }, []);

  if (!loggedIn) {
    return (
      <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: '#1e293b', borderRadius: 16, padding: 40, width: 400, border: '1px solid #334155' }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 24, color: '#fb923c' }}>Admin Portal</h2>
          <p style={{ margin: '0 0 24px', color: '#94a3b8', fontSize: 14 }}>Full system management access</p>
          {error && <p style={{ color: '#f87171', marginBottom: 16 }}>{error}</p>}
          <label style={{ display: 'block', marginBottom: 8, fontSize: 14, color: '#94a3b8' }}>Admin ID</label>
          <input value={loginId} onChange={e => setLoginId(e.target.value)}
            style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', marginBottom: 24, boxSizing: 'border-box' }} />
          <button onClick={handleLogin}
            style={{ width: '100%', padding: 12, borderRadius: 8, background: '#ea580c', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 16, fontWeight: 600 }}>
            Sign In as Admin
          </button>
        </div>
      </div>
    );
  }

  const stats = health?.stats;
  const navItems = [
    { href: '/admin/onboarding', label: 'Onboarding', icon: '🏛', desc: 'Faculties, programmes, courses, terms' },
    { href: '/admin/skills', label: 'Skills', icon: '⚡', desc: 'Official skill registry' },
    { href: '/admin/roles', label: 'Roles', icon: '🎯', desc: 'Vetted role library' },
    { href: '/admin/audit', label: 'Audit Log', icon: '📋', desc: 'Search & inspect audit trail' },
    { href: '/admin/metrics', label: 'Metrics', icon: '📊', desc: 'Usage & reliability analytics' },
  ];

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: '#fb923c' }}>SkillSight</span>
          <span style={{ color: '#475569' }}>|</span>
          <span style={{ color: '#94a3b8' }}>Admin Portal</span>
        </div>
        <button onClick={() => { localStorage.clear(); setLoggedIn(false); setHealth(null); }}
          style={{ padding: '6px 16px', borderRadius: 6, background: '#334155', color: '#94a3b8', border: 'none', cursor: 'pointer' }}>
          Sign Out
        </button>
      </nav>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>System Dashboard</h1>
        <p style={{ color: '#64748b', marginBottom: 32 }}>Full administrative control. All actions are audited.</p>

        {/* System stats */}
        {stats && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 40 }}>
            {[
              { label: 'Documents', value: stats.documents, color: '#60a5fa' },
              { label: 'Chunks', value: stats.chunks, color: '#34d399' },
              { label: 'Active Consents', value: stats.active_consents, color: '#a78bfa' },
              { label: 'Open Reviews', value: stats.open_review_tickets, color: '#fbbf24' },
              { label: 'Users', value: stats.registered_users, color: '#fb923c' },
            ].map(stat => (
              <div key={stat.label} style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155', textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: stat.color }}>{stat.value}</div>
                <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>{stat.label}</div>
              </div>
            ))}
          </div>
        )}
        {loading && <p style={{ color: '#64748b' }}>Loading system stats…</p>}
        {error && <p style={{ color: '#f87171' }}>{error}</p>}

        {/* Navigation cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {navItems.map(item => (
            <Link key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
              <div style={{ background: '#1e293b', borderRadius: 12, padding: 24, border: '1px solid #334155', cursor: 'pointer', height: '100%', boxSizing: 'border-box' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = '#fb923c')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#334155')}
              >
                <div style={{ fontSize: 28, marginBottom: 12 }}>{item.icon}</div>
                <h3 style={{ margin: '0 0 8px', fontSize: 18, color: '#e2e8f0' }}>{item.label}</h3>
                <p style={{ margin: 0, fontSize: 13, color: '#64748b', lineHeight: 1.5 }}>{item.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
