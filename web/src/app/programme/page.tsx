'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { programmeBff, devLogin, getToken, clearToken, BffRole } from '@/lib/bffClient';

interface Programme {
  programme_id: string;
  name: string;
  faculty_id?: string;
  course_count: number;
  created_at?: string;
}

export default function ProgrammePage() {
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loggedIn, setLoggedIn] = useState(false);
  const [loginForm, setLoginForm] = useState({ subject_id: 'prog_leader_demo', programme_id: 'CSCI_MSC' });

  const handleLogin = async () => {
    try {
      await devLogin({
        subject_id: loginForm.subject_id,
        role: 'programme_leader' as BffRole,
        programme_id: loginForm.programme_id,
      });
      setLoggedIn(true);
      loadProgrammes();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Login failed'); }
  };

  const loadProgrammes = async () => {
    setLoading(true);
    try {
      const data = await programmeBff.getProgrammes();
      setProgrammes((data as { programmes: Programme[] }).programmes || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load programmes');
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (getToken()) { setLoggedIn(true); loadProgrammes(); }
    else setLoading(false);
  }, []);

  if (!loggedIn) {
    return (
      <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: '#1e293b', borderRadius: 16, padding: 40, width: 400, border: '1px solid #334155' }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 24, color: '#a78bfa' }}>Programme Leader Portal</h2>
          <p style={{ margin: '0 0 24px', color: '#94a3b8', fontSize: 14 }}>Cross-course analytics – aggregated data only</p>
          {error && <p style={{ color: '#f87171', marginBottom: 16 }}>{error}</p>}
          <label style={{ display: 'block', marginBottom: 8, fontSize: 14, color: '#94a3b8' }}>Leader ID</label>
          <input value={loginForm.subject_id} onChange={e => setLoginForm(f => ({ ...f, subject_id: e.target.value }))}
            style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', marginBottom: 16, boxSizing: 'border-box' }} />
          <label style={{ display: 'block', marginBottom: 8, fontSize: 14, color: '#94a3b8' }}>Programme ID</label>
          <input value={loginForm.programme_id} onChange={e => setLoginForm(f => ({ ...f, programme_id: e.target.value }))}
            style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', marginBottom: 24, boxSizing: 'border-box' }} />
          <button onClick={handleLogin}
            style={{ width: '100%', padding: 12, borderRadius: 8, background: '#7c3aed', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 16, fontWeight: 600 }}>
            Sign In as Programme Leader
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: '#a78bfa' }}>SkillSight</span>
          <span style={{ color: '#475569' }}>|</span>
          <span style={{ color: '#94a3b8' }}>Programme Portal</span>
        </div>
        <button onClick={() => { clearToken(); try { localStorage.removeItem('user'); } catch (e) { console.warn('Failed to clear user from localStorage:', e); } setLoggedIn(false); setProgrammes([]); }}
          style={{ padding: '6px 16px', borderRadius: 6, background: '#334155', color: '#94a3b8', border: 'none', cursor: 'pointer' }}>
          Sign Out
        </button>
      </nav>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Programme Overview</h1>
        <p style={{ color: '#64748b', marginBottom: 32 }}>Cross-course skill coverage and gap analysis. No individual student data shown.</p>

        {loading && <p style={{ color: '#64748b' }}>Loading programmes…</p>}
        {error && <p style={{ color: '#f87171' }}>{error}</p>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 20 }}>
          {programmes.map(prog => (
            <Link key={prog.programme_id} href={`/programme/programmes/${prog.programme_id}`} style={{ textDecoration: 'none' }}>
              <div style={{ background: '#1e293b', borderRadius: 12, padding: 24, border: '1px solid #334155', cursor: 'pointer' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = '#a78bfa')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#334155')}
              >
                <div style={{ fontSize: 12, color: '#a78bfa', fontWeight: 600, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {prog.programme_id}
                </div>
                <h3 style={{ margin: '0 0 16px', fontSize: 18, color: '#e2e8f0' }}>{prog.name}</h3>
                <div style={{ display: 'flex', gap: 24 }}>
                  <div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: '#a78bfa' }}>{prog.course_count}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Courses</div>
                  </div>
                  {prog.faculty_id && (
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: '#94a3b8' }}>{prog.faculty_id}</div>
                      <div style={{ fontSize: 12, color: '#64748b' }}>Faculty</div>
                    </div>
                  )}
                </div>
              </div>
            </Link>
          ))}
          {!loading && programmes.length === 0 && (
            <div style={{ gridColumn: '1/-1', textAlign: 'center', color: '#64748b', padding: 48 }}>
              <p>No programmes found. Contact admin to set up programme context.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
