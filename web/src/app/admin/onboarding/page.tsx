'use client';

import { useState } from 'react';
import { adminBff } from '@/lib/bffClient';

type Entity = 'faculty' | 'programme' | 'course' | 'term';

export default function OnboardingPage() {
  const [activeEntity, setActiveEntity] = useState<Entity>('faculty');
  const [form, setForm] = useState<Record<string, string>>({});
  const [result, setResult] = useState<string>('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    setResult('');
    setError('');
    try {
      let data: unknown;
      if (activeEntity === 'faculty') {
        data = await adminBff.createFaculty({ faculty_id: form.id, name: form.name });
      } else if (activeEntity === 'programme') {
        data = await adminBff.createProgramme({ programme_id: form.id, name: form.name, faculty_id: form.faculty_id });
      } else if (activeEntity === 'course') {
        data = await adminBff.createCourse({
          course_id: form.id, course_name: form.name,
          description: form.description, programme_id: form.programme_id,
          faculty_id: form.faculty_id, term_id: form.term_id,
        });
      } else {
        data = await adminBff.createTerm({ term_id: form.id, label: form.name, start_date: form.start_date, end_date: form.end_date });
      }
      setResult(JSON.stringify(data, null, 2));
      setForm({});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Operation failed');
    } finally {
      setLoading(false);
    }
  };

  const fields: Record<Entity, { key: string; label: string; placeholder?: string }[]> = {
    faculty: [
      { key: 'id', label: 'Faculty ID', placeholder: 'ENG' },
      { key: 'name', label: 'Name', placeholder: 'Engineering Faculty' },
    ],
    programme: [
      { key: 'id', label: 'Programme ID', placeholder: 'CSCI_MSC' },
      { key: 'name', label: 'Name', placeholder: 'MSc Computer Science' },
      { key: 'faculty_id', label: 'Faculty ID', placeholder: 'ENG' },
    ],
    course: [
      { key: 'id', label: 'Course ID', placeholder: 'COMP3000' },
      { key: 'name', label: 'Course Name', placeholder: 'Software Engineering' },
      { key: 'description', label: 'Description (optional)', placeholder: '' },
      { key: 'programme_id', label: 'Programme ID (optional)', placeholder: 'CSCI_MSC' },
      { key: 'faculty_id', label: 'Faculty ID (optional)', placeholder: 'ENG' },
      { key: 'term_id', label: 'Term ID (optional)', placeholder: '2025-26-T1' },
    ],
    term: [
      { key: 'id', label: 'Term ID', placeholder: '2025-26-T1' },
      { key: 'name', label: 'Label', placeholder: '2025-26 Semester 1' },
      { key: 'start_date', label: 'Start Date (YYYY-MM-DD, optional)', placeholder: '2025-09-01' },
      { key: 'end_date', label: 'End Date (YYYY-MM-DD, optional)', placeholder: '2025-12-31' },
    ],
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={() => history.back()} style={{ background: 'none', border: 'none', color: '#fb923c', cursor: 'pointer', fontSize: 14 }}>← Admin</button>
        <span style={{ color: '#475569' }}>|</span>
        <span style={{ color: '#94a3b8' }}>Onboarding</span>
      </nav>

      <div style={{ maxWidth: 700, margin: '48px auto', padding: '0 24px' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Organisation Onboarding</h1>

        {/* Entity selector */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 28, background: '#1e293b', borderRadius: 10, padding: 4, border: '1px solid #334155' }}>
          {(['faculty', 'programme', 'course', 'term'] as Entity[]).map(e => (
            <button key={e} onClick={() => { setActiveEntity(e); setForm({}); setResult(''); setError(''); }}
              style={{
                flex: 1, padding: '8px 12px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 13,
                background: activeEntity === e ? '#fb923c' : 'transparent',
                color: activeEntity === e ? '#fff' : '#64748b',
              }}>
              {e.charAt(0).toUpperCase() + e.slice(1)}
            </button>
          ))}
        </div>

        <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 28 }}>
          <h2 style={{ margin: '0 0 24px', fontSize: 18, fontWeight: 600 }}>Create {activeEntity.charAt(0).toUpperCase() + activeEntity.slice(1)}</h2>

          {fields[activeEntity].map(f => (
            <div key={f.key} style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 14, color: '#94a3b8', marginBottom: 6 }}>{f.label}</label>
              <input
                value={form[f.key] || ''}
                onChange={e => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                placeholder={f.placeholder}
                style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', boxSizing: 'border-box' }}
              />
            </div>
          ))}

          {error && <p style={{ color: '#f87171', marginBottom: 12 }}>{error}</p>}
          {result && (
            <pre style={{ background: '#0f172a', borderRadius: 8, padding: 16, fontSize: 12, color: '#34d399', marginBottom: 16, overflow: 'auto' }}>
              {result}
            </pre>
          )}

          <button onClick={handleSubmit} disabled={loading}
            style={{ padding: '12px 32px', borderRadius: 8, background: '#ea580c', color: '#fff', border: 'none', cursor: loading ? 'not-allowed' : 'pointer', fontSize: 15, fontWeight: 600, opacity: loading ? 0.7 : 1 }}>
            {loading ? 'Creating…' : `Create ${activeEntity.charAt(0).toUpperCase() + activeEntity.slice(1)}`}
          </button>
        </div>
      </div>
    </div>
  );
}
