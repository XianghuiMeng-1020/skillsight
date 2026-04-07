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

  useEffect(() => {
    let cancelled = false;
    (async () => {
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
        timeline.sort((a, b) => (a.date < b.date ? 1 : -1));
        setEvents(timeline);
      } catch {
        setEvents([]);
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
          <h1>Skill Timeline</h1>
          <p>Track how your verified skills evolve over time.</p>
        </div>
        <div className="card">
          <div className="card-content">
            {events.length === 0 ? (
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
