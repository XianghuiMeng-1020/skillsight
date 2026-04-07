'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';

type TimelineEvent = { date: string; title: string; detail?: string };
type RecentAssessmentEvent = {
  created_at?: string;
  completed_at?: string;
  assessment_type?: string;
  score?: number | string;
};

function toRecentAssessmentEvent(value: unknown): RecentAssessmentEvent | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  return {
    created_at: typeof record.created_at === 'string' ? record.created_at : undefined,
    completed_at: typeof record.completed_at === 'string' ? record.completed_at : undefined,
    assessment_type: typeof record.assessment_type === 'string' ? record.assessment_type : undefined,
    score: typeof record.score === 'number' || typeof record.score === 'string' ? record.score : undefined,
  };
}

export default function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const profile = await studentBff.getProfile();
        if (cancelled) return;
        const timeline: TimelineEvent[] = [];
        for (const doc of profile.documents || []) {
          if (doc.created_at) timeline.push({ date: doc.created_at, title: 'Uploaded evidence document', detail: doc.filename });
        }
        for (const evt of profile.recent_assessment_events || []) {
          const parsed = toRecentAssessmentEvent(evt);
          if (!parsed) continue;
          timeline.push({
            date: parsed.created_at || parsed.completed_at || new Date().toISOString(),
            title: `Completed ${parsed.assessment_type || 'skill'} assessment`,
            detail: `Score ${Math.round(Number(parsed.score || 0))}`,
          });
        }
        const roleEvents = profile.recent_role_events || [];
        for (const evt of roleEvents) {
          const roleTitle = String(evt.role_title || evt.role_id || 'role');
          timeline.push({
            date: String(evt.created_at || new Date().toISOString()),
            title: `Updated readiness for ${roleTitle}`,
            detail: `Readiness ${Math.round(Number(evt.score || 0) * 100)}%`,
          });
        }
        const exportEvents = profile.recent_export_events || [];
        for (const evt of exportEvents) {
          const action = String(evt.action || '').replace('bff.export.', '');
          timeline.push({
            date: String(evt.created_at || new Date().toISOString()),
            title: `Exported ${action || 'statement'}`,
          });
        }
        timeline.sort((a, b) => (a.date < b.date ? 1 : -1));
        setEvents(timeline);
      } catch {
        setEvents([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const exportReport = async () => {
    try {
      const data = await studentBff.exportTimelineReport();
      const bytes = atob(data.content_base64);
      const buffer = new Uint8Array(bytes.length);
      for (let i = 0; i < bytes.length; i++) buffer[i] = bytes.charCodeAt(i);
      const blob = new Blob([buffer], { type: data.mime_type || 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = data.filename || 'skillsight_growth_report.pdf';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // noop
    }
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>Skill Timeline</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>Track how your verified skills evolve over time.</p>
          </div>
          <div>
            <button className="btn btn-secondary btn-sm" onClick={exportReport}>Export Growth Report</button>
          </div>
        </div>
        <div className="card">
          <div className="card-content">
            {loading ? (
              [1, 2, 3, 4].map((i) => <div key={i} className="skeleton" style={{ height: 20, marginBottom: 10 }} />)
            ) : events.length === 0 ? (
              <p>No timeline events yet.</p>
            ) : (
              <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {events.map((e, idx) => (
                  <li key={`${e.date}-${idx}`} style={{ borderLeft: '2px solid var(--sage)', padding: '0.25rem 0 0.75rem 0.75rem', marginLeft: '0.5rem' }}>
                    <div style={{ fontSize: 12, color: 'var(--gray-500)' }}>{new Date(e.date).toLocaleString()}</div>
                    <div style={{ fontWeight: 600 }}>{e.title}</div>
                    {e.detail ? <div style={{ color: 'var(--gray-600)' }}>{e.detail}</div> : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
