'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { adminBff, getToken } from '@/lib/bffClient';

interface ChangeLogItem {
  id: string;
  scope?: string;
  subject_id?: string;
  event_type: string;
  entity_key?: string;
  created_at: string;
  summary: string;
  before_state: Record<string, unknown>;
  after_state: Record<string, unknown>;
  diff: Record<string, unknown>;
  why: Record<string, unknown>;
  request_id?: string;
  actor_role?: string;
}

const EVENT_LABELS: Record<string, string> = {
  skill_changed: '技能变化',
  role_readiness_changed: '角色就绪度',
  consent_withdrawn: '同意撤回',
  document_deleted: '文档删除',
  actions_changed: '动作更新',
};

export default function AdminChangeLogPage() {
  const [items, setItems] = useState<ChangeLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [subjectId, setSubjectId] = useState('');
  const [eventType, setEventType] = useState('');
  const [requestId, setRequestId] = useState('');

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      if (!token) {
        setError('Please log in as admin.');
        setItems([]);
        return;
      }
      const params: Record<string, string> = { limit: '50' };
      if (subjectId) params.subject_id = subjectId;
      if (eventType) params.event_type = eventType;
      if (requestId) params.request_id = requestId;
      const res = await adminBff.changeLogSearch(params);
      setItems((res.items || []) as ChangeLogItem[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load change log');
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const toggleExpanded = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">Change Log (Admin)</h1>
            <p className="page-subtitle">
              治理审计：按 subject_id / event_type / request_id 过滤
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={fetchData}>↻ 刷新</button>
        </div>

        <div className="page-content">
          {/* Filters */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-content" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <label>
                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>subject_id</span>
                <input
                  type="text"
                  value={subjectId}
                  onChange={e => setSubjectId(e.target.value)}
                  placeholder="Filter by subject"
                  style={{ display: 'block', marginTop: 4, padding: '0.5rem', width: 180, borderRadius: 6, border: '1px solid var(--gray-200)' }}
                />
              </label>
              <label>
                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>event_type</span>
                <select
                  value={eventType}
                  onChange={e => setEventType(e.target.value)}
                  style={{ display: 'block', marginTop: 4, padding: '0.5rem', width: 180, borderRadius: 6, border: '1px solid var(--gray-200)' }}
                >
                  <option value="">All</option>
                  {Object.keys(EVENT_LABELS).map(et => (
                    <option key={et} value={et}>{EVENT_LABELS[et]}</option>
                  ))}
                </select>
              </label>
              <label>
                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>request_id</span>
                <input
                  type="text"
                  value={requestId}
                  onChange={e => setRequestId(e.target.value)}
                  placeholder="Filter by request"
                  style={{ display: 'block', marginTop: 4, padding: '0.5rem', width: 220, borderRadius: 6, border: '1px solid var(--gray-200)' }}
                />
              </label>
              <button className="btn btn-primary btn-sm" onClick={fetchData}>查询</button>
            </div>
          </div>

          {loading ? (
            <div className="loading"><span className="spinner"></span> 加载中...</div>
          ) : error ? (
            <div className="alert alert-error">
              <span>⚠</span>
              <div>
                <strong>加载失败</strong>
                <p style={{ marginTop: '0.25rem', fontSize: '0.875rem' }}>{error}</p>
              </div>
            </div>
          ) : items.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-icon">📜</div>
                <div className="empty-title">暂无变更事件</div>
                <div className="empty-desc">尝试放宽筛选条件后重试。</div>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {items.map(item => {
                const isExp = expanded.has(item.id);
                const eventLabel = EVENT_LABELS[item.event_type] ?? item.event_type;
                return (
                  <div key={item.id} className="card">
                    <div className="card-content" style={{ cursor: 'pointer' }} onClick={() => toggleExpanded(item.id)}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <span style={{ fontWeight: 600 }}>{item.summary}</span>
                        <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                          {new Date(item.created_at).toLocaleString('zh-CN')} · {eventLabel}
                          {item.subject_id && <span> · {item.subject_id}</span>}
                          {item.entity_key && <span> · {item.entity_key}</span>}
                        </span>
                      </div>
                      {isExp && (
                        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--gray-100)' }}>
                          <pre style={{ padding: '0.5rem', background: 'var(--gray-50)', borderRadius: 6, overflow: 'auto', maxHeight: 200, fontSize: '0.8rem' }}>
                            {JSON.stringify({
                              before_state: item.before_state,
                              after_state: item.after_state,
                              diff: item.diff,
                              why: item.why,
                              request_id: item.request_id,
                              actor_role: item.actor_role,
                            }, null, 2)}
                          </pre>
                        </div>
                      )}
                      <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-400)' }}>
                        {isExp ? '▲ 收起' : '▼ 展开 JSON'}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
