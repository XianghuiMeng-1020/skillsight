'use client';

import { useState } from 'react';
import { adminBff } from '@/lib/bffClient';

interface AuditEntry {
  audit_id: string;
  request_id?: string;
  subject_id?: string;
  action: string;
  object_type?: string;
  object_id?: string;
  status?: string;
  error?: string;
  created_at?: string;
}

export default function AuditPage() {
  const [filters, setFilters] = useState({ action: '', status: '', request_id: '', limit: '50' });
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const search = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await adminBff.searchAudit({
        action: filters.action || undefined,
        status: filters.status || undefined,
        request_id: filters.request_id || undefined,
        limit: parseInt(filters.limit) || 50,
      });
      setEntries((data as { items: AuditEntry[] }).items || []);
      setCount((data as { count: number }).count || 0);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally { setLoading(false); }
  };

  const statusColor = (s?: string) => s === 'ok' ? '#34d399' : s === 'error' ? '#f87171' : '#64748b';

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={() => history.back()} style={{ background: 'none', border: 'none', color: '#fb923c', cursor: 'pointer', fontSize: 14 }}>← Admin</button>
        <span style={{ color: '#475569' }}>|</span>
        <span style={{ color: '#94a3b8' }}>Audit Log</span>
      </nav>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Audit Log Search</h1>

        <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 24, marginBottom: 24 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 16 }}>
            {[
              { key: 'action', label: 'Action (partial)', placeholder: 'bff.staff' },
              { key: 'status', label: 'Status', placeholder: 'ok / error' },
              { key: 'request_id', label: 'Request ID', placeholder: '' },
              { key: 'limit', label: 'Limit', placeholder: '50' },
            ].map(f => (
              <div key={f.key}>
                <label style={{ display: 'block', fontSize: 13, color: '#94a3b8', marginBottom: 6 }}>{f.label}</label>
                <input value={filters[f.key as keyof typeof filters]}
                  onChange={e => setFilters(prev => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0', boxSizing: 'border-box', fontSize: 13 }} />
              </div>
            ))}
          </div>
          <button onClick={search} disabled={loading}
            style={{ padding: '10px 28px', borderRadius: 8, background: '#ea580c', color: '#fff', border: 'none', cursor: loading ? 'not-allowed' : 'pointer', fontWeight: 600, opacity: loading ? 0.7 : 1 }}>
            {loading ? 'Searching…' : 'Search Audit Log'}
          </button>
        </div>

        {error && <p style={{ color: '#f87171', marginBottom: 16 }}>{error}</p>}
        {entries.length > 0 && <p style={{ color: '#64748b', marginBottom: 16 }}>Found {count} entries (showing {entries.length})</p>}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {entries.map(entry => (
            <div key={entry.audit_id} style={{ background: '#1e293b', borderRadius: 10, padding: '14px 20px', border: '1px solid #334155' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <span style={{ fontWeight: 600, color: '#e2e8f0', fontSize: 14 }}>{entry.action}</span>
                  {entry.object_type && <span style={{ fontSize: 12, color: '#64748b', marginLeft: 8 }}>→ {entry.object_type}{entry.object_id ? `:${entry.object_id.slice(0, 8)}` : ''}</span>}
                </div>
                <span style={{ fontSize: 12, fontWeight: 600, color: statusColor(entry.status), background: `${statusColor(entry.status)}15`, padding: '2px 10px', borderRadius: 12 }}>
                  {entry.status || 'unknown'}
                </span>
              </div>
              <div style={{ fontSize: 12, color: '#64748b', display: 'flex', gap: 16 }}>
                <span>ID: {entry.audit_id.slice(0, 8)}…</span>
                {entry.request_id && <span>req: {entry.request_id.slice(0, 8)}</span>}
                {entry.created_at && <span>{new Date(entry.created_at).toLocaleString()}</span>}
              </div>
              {entry.error && <div style={{ fontSize: 12, color: '#f87171', marginTop: 6 }}>{entry.error}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
