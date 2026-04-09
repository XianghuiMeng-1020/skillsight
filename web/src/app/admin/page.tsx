'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { adminBff, devLogin, getToken, BffRole } from '@/lib/bffClient';
import { useTheme } from '@/lib/contexts';

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
  const { theme } = useTheme();
  const isDark = theme === 'dark';
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
      <div className="app-container" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: 'var(--card-bg, #fff)', borderRadius: 16, padding: 40, width: 400, border: '1px solid var(--border, #e7e5e4)', boxShadow: '0 8px 32px rgba(0,0,0,0.08)' }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 24, color: '#E18182' }}>Admin Portal</h2>
          <p style={{ margin: '0 0 24px', color: 'var(--gray-600)', fontSize: 14 }}>Full system management access</p>
          {error && <p style={{ color: '#ef4444', marginBottom: 16 }}>{error}</p>}
          <label style={{ display: 'block', marginBottom: 8, fontSize: 14, color: 'var(--gray-600)' }}>Admin ID</label>
          <input value={loginId} onChange={e => setLoginId(e.target.value)}
            style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid var(--border, #e7e5e4)', background: 'var(--bg, #fff)', color: 'var(--text, #1c1917)', marginBottom: 24, boxSizing: 'border-box' }} />
          <button onClick={handleLogin}
            style={{ width: '100%', padding: 12, borderRadius: 8, background: '#E18182', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 16, fontWeight: 600 }}>
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
    <div className="app-container" style={{ minHeight: '100vh' }}>
      <nav style={{ background: 'var(--card-bg, #fff)', borderBottom: '1px solid var(--border, #e7e5e4)', padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: '#E18182' }}>SkillSight</span>
          <span style={{ color: 'var(--gray-400)' }}>|</span>
          <span style={{ color: 'var(--gray-600)' }}>Admin Portal</span>
        </div>
        <button
          onClick={() => {
            localStorage.removeItem('skillsight_token');
            localStorage.removeItem('skillsight_role');
            localStorage.removeItem('user');
            setLoggedIn(false);
            setHealth(null);
          }}
          style={{ padding: '6px 16px', borderRadius: 6, background: isDark ? '#334155' : '#f5f5f4', color: 'var(--gray-600)', border: '1px solid var(--border, #e7e5e4)', cursor: 'pointer' }}>
          Sign Out
        </button>
      </nav>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>System Dashboard</h1>
        <p style={{ color: 'var(--gray-600)', marginBottom: 32 }}>Full administrative control. All actions are audited.</p>

        {stats && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16, marginBottom: 40 }}>
            {[
              { label: 'Documents', value: stats.documents, color: '#E18182' },
              { label: 'Chunks', value: stats.chunks, color: '#98B8A8' },
              { label: 'Active Consents', value: stats.active_consents, color: '#C9DDE3' },
              { label: 'Open Reviews', value: stats.open_review_tickets, color: '#F9CE9C' },
              { label: 'Users', value: stats.registered_users, color: '#BBCFC3' },
            ].map(stat => (
              <div key={stat.label} style={{ background: 'var(--card-bg, #fff)', borderRadius: 12, padding: 20, border: '1px solid var(--border, #e7e5e4)', textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: stat.color }}>{stat.value}</div>
                <div style={{ fontSize: 13, color: 'var(--gray-600)', marginTop: 4 }}>{stat.label}</div>
              </div>
            ))}
          </div>
        )}
        {loading && <p style={{ color: 'var(--gray-600)' }}>Loading system stats…</p>}
        {error && <p style={{ color: '#ef4444' }}>{error}</p>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {navItems.map(item => (
            <Link key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
              <div style={{ background: 'var(--card-bg, #fff)', borderRadius: 12, padding: 24, border: '1px solid var(--border, #e7e5e4)', cursor: 'pointer', height: '100%', boxSizing: 'border-box', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', transition: 'border-color 0.2s, box-shadow 0.2s' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = '#E18182'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(225,129,130,0.15)'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border, #e7e5e4)'; e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.04)'; }}
              >
                <div style={{ fontSize: 28, marginBottom: 12 }}>{item.icon}</div>
                <h3 style={{ margin: '0 0 8px', fontSize: 18, color: 'var(--text, #1c1917)' }}>{item.label}</h3>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--gray-600)', lineHeight: 1.5 }}>{item.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
