'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { staffBff, devLogin, getToken, setToken, clearToken, BffRole } from '@/lib/bffClient';

interface Course {
  course_id: string;
  course_name: string;
  description?: string;
  programme_id?: string;
  term_id?: string;
  mapped_skills_count: number;
  open_review_tickets: number;
}

export default function StaffPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loggedIn, setLoggedIn] = useState(false);
  const [loginForm, setLoginForm] = useState({
    subject_id: 'staff_demo',
    course_ids: 'COMP3000',
  });

  const handleLogin = async () => {
    try {
      await devLogin({
        subject_id: loginForm.subject_id,
        role: 'staff' as BffRole,
        course_ids: loginForm.course_ids.split(',').map(s => s.trim()).filter(Boolean),
        term_id: '2025-26-T1',
      });
      setLoggedIn(true);
      loadCourses();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Login failed');
    }
  };

  const loadCourses = async () => {
    setLoading(true);
    try {
      const data = await staffBff.getCourses();
      setCourses(data.courses as Course[]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load courses');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const token = getToken();
    if (token) { setLoggedIn(true); loadCourses(); }
    else setLoading(false);
  }, []);

  if (!loggedIn) {
    return (
      <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: '#1e293b', borderRadius: 16, padding: 40, width: 400, border: '1px solid #334155' }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 24, color: '#60a5fa' }}>Instructor / TA Portal</h2>
          <p style={{ margin: '0 0 24px', color: '#94a3b8', fontSize: 14 }}>Staff BFF – Teaching Support</p>
          {error && <p style={{ color: '#f87171', marginBottom: 16 }}>{error}</p>}
          <label style={{ display: 'block', marginBottom: 8, fontSize: 14, color: '#94a3b8' }}>Staff ID</label>
          <input
            value={loginForm.subject_id}
            onChange={e => setLoginForm(f => ({ ...f, subject_id: e.target.value }))}
            style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', marginBottom: 16, boxSizing: 'border-box' }}
          />
          <label style={{ display: 'block', marginBottom: 8, fontSize: 14, color: '#94a3b8' }}>Course IDs (comma separated)</label>
          <input
            value={loginForm.course_ids}
            onChange={e => setLoginForm(f => ({ ...f, course_ids: e.target.value }))}
            placeholder="COMP3000, COMP3100"
            style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', marginBottom: 24, boxSizing: 'border-box' }}
          />
          <button
            onClick={handleLogin}
            style={{ width: '100%', padding: '12px', borderRadius: 8, background: '#2563eb', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 16, fontWeight: 600 }}
          >
            Sign In as Instructor
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: '#60a5fa' }}>SkillSight</span>
          <span style={{ color: '#475569' }}>|</span>
          <span style={{ color: '#94a3b8' }}>Instructor Portal</span>
        </div>
        <button
          onClick={() => { clearToken(); localStorage.removeItem('user'); setLoggedIn(false); setCourses([]); }}
          style={{ padding: '6px 16px', borderRadius: 6, background: '#334155', color: '#94a3b8', border: 'none', cursor: 'pointer' }}
        >
          Sign Out
        </button>
      </nav>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>My Courses</h1>
        <p style={{ color: '#64748b', marginBottom: 32 }}>Aggregated skill coverage and review queue for your teaching scope.</p>

        {loading && <p style={{ color: '#64748b' }}>Loading courses…</p>}
        {error && <p style={{ color: '#f87171' }}>{error}</p>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 20 }}>
          {courses.map(course => (
            <Link
              key={course.course_id}
              href={`/staff/courses/${course.course_id}`}
              style={{ textDecoration: 'none' }}
            >
              <div style={{
                background: '#1e293b',
                borderRadius: 12,
                padding: 24,
                border: '1px solid #334155',
                transition: 'border-color 0.2s',
                cursor: 'pointer',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = '#60a5fa')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = '#334155')}
              >
                <div style={{ fontSize: 12, color: '#60a5fa', fontWeight: 600, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {course.course_id}
                </div>
                <h3 style={{ margin: '0 0 8px', fontSize: 18, color: '#e2e8f0' }}>{course.course_name}</h3>
                {course.description && (
                  <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: 14, lineHeight: 1.5 }}>{course.description}</p>
                )}
                <div style={{ display: 'flex', gap: 16 }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: '#34d399' }}>{course.mapped_skills_count}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Skills Mapped</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: course.open_review_tickets > 0 ? '#fbbf24' : '#64748b' }}>
                      {course.open_review_tickets}
                    </div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Open Reviews</div>
                  </div>
                </div>
              </div>
            </Link>
          ))}
          {!loading && courses.length === 0 && (
            <div style={{ gridColumn: '1/-1', textAlign: 'center', color: '#64748b', padding: 48 }}>
              <p>No courses found. Contact admin to set up teaching relations.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
