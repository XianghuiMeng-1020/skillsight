'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { staffBff } from '@/lib/bffClient';
import { fmt2 } from '@/lib/formatNumber';

interface SkillSummary {
  skill_id: string;
  canonical_name: string;
  required_level?: string;
  review_status: string;
  evidence_count: number;
  demonstrated_count: number;
}

interface ReviewTicket {
  ticket_id: string;
  created_at: string;
  status: string;
  skill_id?: string;
  uncertainty_reason?: string;
  draft_label?: string;
  evidence_pointers?: unknown[];
  resolved_at?: string;
}

export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const [skillsSummary, setSkillsSummary] = useState<SkillSummary[]>([]);
  const [tickets, setTickets] = useState<ReviewTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'skills' | 'reviews'>('skills');

  useEffect(() => {
    const load = async () => {
      try {
        const [summary, queue] = await Promise.all([
          staffBff.getCourseSkillsSummary(courseId),
          staffBff.getReviewQueue(courseId),
        ]);
        setSkillsSummary((summary as { skills: SkillSummary[] }).skills || []);
        setTickets((queue as { tickets: ReviewTicket[] }).tickets || []);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load course data');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [courseId]);

  const statusColor = (status: string) => {
    if (status === 'approved') return '#34d399';
    if (status === 'rejected') return '#f87171';
    if (status === 'open') return '#fbbf24';
    return '#64748b';
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <Link href="/staff" style={{ color: '#60a5fa', textDecoration: 'none', fontSize: 14 }}>← My Courses</Link>
        <span style={{ color: '#475569' }}>|</span>
        <span style={{ color: '#94a3b8' }}>{courseId}</span>
      </nav>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 4 }}>{courseId}</h1>
        <p style={{ color: '#64748b', marginBottom: 32, fontSize: 14 }}>
          Aggregate view only – no individual student data displayed.
        </p>

        {/* Tab selector */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 28, background: '#1e293b', borderRadius: 10, padding: 4, width: 'fit-content', border: '1px solid #334155' }}>
          {(['skills', 'reviews'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '8px 24px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 14,
                background: activeTab === tab ? '#2563eb' : 'transparent',
                color: activeTab === tab ? '#fff' : '#64748b',
              }}
            >
              {tab === 'skills' ? `Skills Summary (${skillsSummary.length})` : `Review Queue (${tickets.filter(t => t.status === 'open').length})`}
            </button>
          ))}
        </div>

        {loading && <p style={{ color: '#64748b' }}>Loading…</p>}
        {error && <p style={{ color: '#f87171' }}>{error}</p>}

        {activeTab === 'skills' && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {skillsSummary.map(skill => (
              <div key={skill.skill_id} style={{ background: '#1e293b', borderRadius: 10, padding: 20, border: '1px solid #334155' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontSize: 12, color: '#60a5fa', fontWeight: 600, marginBottom: 4 }}>{skill.skill_id}</div>
                    <h3 style={{ margin: 0, fontSize: 16, color: '#e2e8f0' }}>{skill.canonical_name}</h3>
                    {skill.required_level && (
                      <span style={{ fontSize: 12, color: '#64748b', marginTop: 4, display: 'block' }}>Required: {skill.required_level}</span>
                    )}
                  </div>
                  <span style={{ padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: `${statusColor(skill.review_status)}20`, color: statusColor(skill.review_status) }}>
                    {skill.review_status}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 24, marginTop: 16 }}>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#60a5fa' }}>{fmt2(skill.evidence_count)}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Evidence Items</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#34d399' }}>{fmt2(skill.demonstrated_count)}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Demonstrated</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#e2e8f0' }}>
                      {skill.evidence_count > 0 ? fmt2((skill.demonstrated_count / skill.evidence_count) * 100) : fmt2(0)}%
                    </div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Coverage</div>
                  </div>
                </div>
              </div>
            ))}
            {skillsSummary.length === 0 && (
              <p style={{ color: '#64748b', textAlign: 'center', padding: 48 }}>No skills mapped to this course yet.</p>
            )}
          </div>
        )}

        {activeTab === 'reviews' && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {tickets.map(ticket => (
              <Link key={ticket.ticket_id} href={`/staff/review/${ticket.ticket_id}`} style={{ textDecoration: 'none' }}>
                <div style={{ background: '#1e293b', borderRadius: 10, padding: 20, border: '1px solid #334155', cursor: 'pointer' }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = '#60a5fa')}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = '#334155')}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>
                        {new Date(ticket.created_at).toLocaleDateString()} · Skill: {ticket.skill_id || 'N/A'}
                      </div>
                      <p style={{ margin: 0, color: '#fbbf24', fontSize: 14 }}>
                        {ticket.uncertainty_reason || 'Review required'}
                      </p>
                      {ticket.draft_label && (
                        <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                          Draft: <span style={{ color: '#94a3b8' }}>{ticket.draft_label}</span>
                        </div>
                      )}
                      <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                        Evidence pointers: {(ticket.evidence_pointers || []).length}
                      </div>
                    </div>
                    <span style={{ padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: `${statusColor(ticket.status)}20`, color: statusColor(ticket.status) }}>
                      {ticket.status}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
            {tickets.length === 0 && (
              <p style={{ color: '#64748b', textAlign: 'center', padding: 48 }}>No review tickets for this course.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
