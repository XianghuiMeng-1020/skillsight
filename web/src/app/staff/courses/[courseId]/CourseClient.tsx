'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { staffBff } from '@/lib/bffClient';
import { fmt2 } from '@/lib/formatNumber';
import { useLanguage } from '@/lib/contexts';
import styles from './CourseClient.module.css';

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
  const { t } = useLanguage();
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
        setError(e instanceof Error ? e.message : t('staff.courseLoadError'));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [courseId, t]);

  const statusColor = (status: string) => {
    if (status === 'approved') return 'var(--success)';
    if (status === 'rejected') return 'var(--error)';
    if (status === 'open') return 'var(--warning)';
    return 'var(--gray-500)';
  };

  return (
    <div className={styles.root}>
      <nav className={styles.nav}>
        <Link href="/staff" style={{ color: 'var(--primary)', textDecoration: 'none', fontSize: 14 }}>
          {t('staff.backCourses')}
        </Link>
        <span style={{ color: 'var(--gray-300)' }}>|</span>
        <span style={{ color: 'var(--gray-600)' }}>{courseId}</span>
      </nav>

      <div className={styles.main}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 4 }}>{courseId}</h1>
        <p style={{ color: 'var(--gray-500)', marginBottom: 32, fontSize: 14 }}>
          {t('staff.aggregateView')}
        </p>

        <div className={styles.tabBar}>
          {(['skills', 'reviews'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              className={`${styles.tabBtn} ${activeTab === tab ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'skills'
                ? t('staff.tabSkills').replace('{n}', String(skillsSummary.length))
                : t('staff.tabReviews').replace('{n}', String(tickets.filter((x) => x.status === 'open').length))}
            </button>
          ))}
        </div>

        {loading && <p style={{ color: 'var(--gray-500)' }}>{t('common.loading')}</p>}
        {error && <p style={{ color: 'var(--error)' }}>{error}</p>}

        {activeTab === 'skills' && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {skillsSummary.map((skill) => (
              <div key={skill.skill_id} className={styles.card}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--primary)', fontWeight: 600, marginBottom: 4 }}>{skill.skill_id}</div>
                    <h3 style={{ margin: 0, fontSize: 16, color: 'var(--gray-900)' }}>{skill.canonical_name}</h3>
                    {skill.required_level && (
                      <span style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4, display: 'block' }}>
                        {t('staff.required')}: {skill.required_level}
                      </span>
                    )}
                  </div>
                  <span
                    style={{
                      padding: '4px 12px',
                      borderRadius: 20,
                      fontSize: 12,
                      fontWeight: 600,
                      background: `${statusColor(skill.review_status)}22`,
                      color: statusColor(skill.review_status),
                    }}
                  >
                    {skill.review_status}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 24, marginTop: 16 }}>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--primary)' }}>{fmt2(skill.evidence_count)}</div>
                    <div style={{ fontSize: 12, color: 'var(--gray-500)' }}>{t('staff.evidenceItems')}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--success)' }}>{fmt2(skill.demonstrated_count)}</div>
                    <div style={{ fontSize: 12, color: 'var(--gray-500)' }}>{t('staff.demonstrated')}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--gray-800)' }}>
                      {skill.evidence_count > 0 ? fmt2((skill.demonstrated_count / skill.evidence_count) * 100) : fmt2(0)}%
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--gray-500)' }}>{t('staff.coverage')}</div>
                  </div>
                </div>
              </div>
            ))}
            {skillsSummary.length === 0 && (
              <p style={{ color: 'var(--gray-500)', textAlign: 'center', padding: 48 }}>{t('staff.noSkills')}</p>
            )}
          </div>
        )}

        {activeTab === 'reviews' && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {tickets.map((ticket) => (
              <Link key={ticket.ticket_id} href={`/staff/review/${ticket.ticket_id}`} className={styles.ticketLink}>
                <div className={styles.ticketCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ fontSize: 12, color: 'var(--gray-500)', marginBottom: 4 }}>
                        {new Date(ticket.created_at).toLocaleDateString()} · {t('staff.skillLabel')}{' '}
                        {ticket.skill_id || 'N/A'}
                      </div>
                      <p style={{ margin: 0, color: 'var(--warning)', fontSize: 14 }}>
                        {ticket.uncertainty_reason || t('staff.reviewRequired')}
                      </p>
                      {ticket.draft_label && (
                        <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>
                          {t('staff.draft')}: <span style={{ color: 'var(--gray-600)' }}>{ticket.draft_label}</span>
                        </div>
                      )}
                      <div style={{ fontSize: 12, color: 'var(--gray-500)', marginTop: 4 }}>
                        {t('staff.evidencePointers')}: {(ticket.evidence_pointers || []).length}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: '4px 12px',
                        borderRadius: 20,
                        fontSize: 12,
                        fontWeight: 600,
                        background: `${statusColor(ticket.status)}22`,
                        color: statusColor(ticket.status),
                      }}
                    >
                      {ticket.status}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
            {tickets.length === 0 && (
              <p style={{ color: 'var(--gray-500)', textAlign: 'center', padding: 48 }}>{t('staff.noTickets')}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
