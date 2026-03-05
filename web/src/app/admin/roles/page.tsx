'use client';

import { useState, useEffect } from 'react';
import { adminBff } from '@/lib/bffClient';

interface Role { role_id: string; role_title: string; description?: string }

export default function AdminRolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [importJson, setImportJson] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState('');

  const loadRoles = async () => {
    setLoading(true);
    try {
      const data = await adminBff.getRoles(200);
      setRoles((data as { roles: Role[] }).roles || []);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Failed'); }
    finally { setLoading(false); }
  };

  const handleImport = async () => {
    setImporting(true);
    setImportResult('');
    setError('');
    try {
      const parsed = JSON.parse(importJson);
      const rolesArr = Array.isArray(parsed) ? parsed : parsed.roles;
      const data = await adminBff.importRoles(rolesArr);
      setImportResult(JSON.stringify(data, null, 2));
      setImportJson('');
      loadRoles();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Import failed'); }
    finally { setImporting(false); }
  };

  useEffect(() => { loadRoles(); }, []);

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={() => history.back()} style={{ background: 'none', border: 'none', color: '#fb923c', cursor: 'pointer', fontSize: 14 }}>← Admin</button>
        <span style={{ color: '#475569' }}>|</span>
        <span style={{ color: '#94a3b8' }}>Role Library</span>
      </nav>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Vetted Role Library</h1>
        <p style={{ color: '#64748b', marginBottom: 32 }}>{roles.length} roles in library</p>

        {loading && <p style={{ color: '#64748b' }}>Loading…</p>}
        {error && <p style={{ color: '#f87171', marginBottom: 16 }}>{error}</p>}

        <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 24, marginBottom: 28 }}>
          <h2 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>Import Roles (JSON)</h2>
          <textarea value={importJson} onChange={e => setImportJson(e.target.value)} rows={5}
            placeholder='[{"role_id": "R001", "role_title": "Software Engineer", "description": "..."}]'
            style={{ width: '100%', padding: 12, borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', fontSize: 13, fontFamily: 'monospace', resize: 'vertical', boxSizing: 'border-box', marginBottom: 12 }} />
          {importResult && <pre style={{ background: '#0f172a', borderRadius: 8, padding: 12, fontSize: 12, color: '#34d399', marginBottom: 12, overflow: 'auto' }}>{importResult}</pre>}
          <button onClick={handleImport} disabled={importing || !importJson.trim()}
            style={{ padding: '10px 24px', borderRadius: 8, background: '#ea580c', color: '#fff', border: 'none', cursor: importing ? 'not-allowed' : 'pointer', fontWeight: 600, opacity: importing ? 0.7 : 1 }}>
            {importing ? 'Importing…' : 'Import Roles'}
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {roles.map(role => (
            <div key={role.role_id} style={{ background: '#1e293b', borderRadius: 10, padding: '14px 20px', border: '1px solid #334155' }}>
              <span style={{ fontSize: 12, color: '#a78bfa', fontWeight: 600, fontFamily: 'monospace' }}>{role.role_id}</span>
              <div style={{ fontWeight: 600, color: '#e2e8f0', fontSize: 15, marginTop: 2 }}>{role.role_title}</div>
              {role.description && <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>{role.description}</div>}
            </div>
          ))}
          {!loading && roles.length === 0 && <p style={{ color: '#64748b', textAlign: 'center', padding: 48 }}>No roles in library.</p>}
        </div>
      </div>
    </div>
  );
}
