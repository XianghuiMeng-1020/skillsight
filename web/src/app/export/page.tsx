'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useLanguage, getDateLocale } from '@/lib/contexts';
import { studentBff, getToken, type ExportStatementResponse } from '@/lib/bffClient';

interface EvidenceItem {
  chunk_id: string;
  snippet: string;
  section_path?: string;
  page_start?: number;
  doc_id: string;
}

interface SkillEntry {
  skill_id: string;
  canonical_name: string;
  label: string;
  rationale?: string;
  evidence_items: EvidenceItem[];
}

export default function ExportPage() {
  const { t, language } = useLanguage();
  const locale = getDateLocale(language);
  const [data, setData] = useState<ExportStatementResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const printRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!getToken()) {
      setLoading(false);
      setError(t('export.notLoggedIn'));
      return;
    }
    studentBff.exportStatement()
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : t('export.failedToLoad')))
      .finally(() => setLoading(false));
  }, []);

  const handlePrint = () => window.print();

  const demonstratedSkills = data?.statement.skills.filter(
    s => s.label === 'demonstrated' || s.label === 'mentioned'
  ) ?? [];

  return (
    <div>
      {/* Nav bar (hidden on print) */}
      <div className="no-print" style={{
        padding: '0.75rem 1.5rem',
        borderBottom: '1px solid var(--gray-200)',
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        background: 'white',
      }}>
        <Link href="/dashboard/skills" style={{ color: 'var(--gray-500)', fontSize: '0.875rem', textDecoration: 'none' }}>
          {t('export.back')}
        </Link>
        <span style={{ flex: 1, fontWeight: 600, fontSize: '0.9375rem' }}>{t('export.title')}</span>
        <button
          onClick={handlePrint}
          disabled={loading || !!error}
          style={{
            padding: '0.5rem 1.25rem',
            background: 'var(--primary)',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: loading || !!error ? 'not-allowed' : 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
          }}
        >
          {t('export.print')}
        </button>
      </div>

      {data && !loading && !error && (
        <>
        <div className="no-print" style={{ maxWidth: '800px', margin: '0 auto', padding: '0.75rem 1.5rem', fontSize: '0.8125rem', color: 'var(--gray-600)' }}>
          {t('export.certificateNote')}
          {data.verification_token && (
            <p style={{ marginTop: '0.5rem' }}>
              {t('export.verifyLabel')}:{' '}
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || ''}/bff/student/export/verify?token=${encodeURIComponent(data.verification_token)}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ wordBreak: 'break-all', color: 'var(--primary)' }}
              >
                {t('export.verifyLink')}
              </a>
            </p>
          )}
        </div>
        </>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          <div className="spinner" style={{ margin: '0 auto 1rem' }}></div>
          {t('export.generating')}
        </div>
      )}

      {error && (
        <div style={{ maxWidth: '600px', margin: '2rem auto', padding: '1rem 1.25rem', background: '#ffecec', borderRadius: '12px', border: '1px solid #f5c2c2' }}>
          <strong style={{ color: '#b42318' }}>{t('export.loadFailed')}</strong>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem', color: '#7f1d1d' }}>{error}</p>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.813rem', color: '#7f1d1d' }}>
            {t('export.loadFailedMsg')}
          </p>
        </div>
      )}

      {/* Printable Statement */}
      {data && (
        <div ref={printRef} style={{
          maxWidth: '800px',
          margin: '2rem auto',
          padding: '2.5rem',
          background: 'white',
          fontFamily: 'Georgia, serif',
        }}>
          {/* Header */}
          <div style={{
            borderBottom: '3px solid var(--primary, #E18182)',
            paddingBottom: '1.5rem',
            marginBottom: '2rem',
          }}>
            <div style={{ fontSize: '0.75rem', color: '#888', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
              SkillSight · HKU Skills-to-Jobs Transparency System
            </div>
            <h1 style={{ fontSize: '2rem', fontWeight: 700, margin: '0 0 0.25rem', color: '#1a1a1a' }}>
              {t('export.skillsStatement')}
            </h1>
            <div style={{ fontSize: '0.8rem', color: '#666', marginBottom: '0.5rem' }}>{t('share.certificate')}</div>
            <div style={{ fontSize: '0.9rem', color: '#555' }}>
              <span>{t('export.studentId')}<strong>{data.subject_id}</strong></span>
              <span style={{ margin: '0 1rem' }}>·</span>
              <span>{t('export.generated')}<strong>{new Date(data.generated_at).toLocaleString(locale)}</strong></span>
            </div>
          </div>

          {/* Summary */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem',
            marginBottom: '2rem',
          }}>
            {[
              { labelKey: 'export.skillsAssessed', value: data.statement.total_skills_assessed },
              { labelKey: 'export.skillsDemonstrated', value: data.statement.demonstrated_skills },
              { labelKey: 'export.evidenceItems', value: data.statement.total_evidence_items },
            ].map(stat => (
              <div key={stat.labelKey} style={{
                padding: '1rem', border: '1px solid #e8e8e8', borderRadius: '8px', textAlign: 'center',
              }}>
                <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--primary, #E18182)' }}>
                  {stat.value}
                </div>
                <div style={{ fontSize: '0.8rem', color: '#777' }}>{t(stat.labelKey)}</div>
              </div>
            ))}
          </div>

          {/* Evidence Sources */}
          {data.statement.documents.length > 0 && (
            <div style={{ marginBottom: '2rem' }}>
              <h2 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: '0.75rem', color: '#1a1a1a' }}>
                {t('export.evidenceSources')}
              </h2>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ background: '#f8f8f8' }}>
                    <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', borderBottom: '1px solid #e8e8e8' }}>{t('export.filename')}</th>
                    <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', borderBottom: '1px solid #e8e8e8' }}>{t('export.consent')}</th>
                    <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', borderBottom: '1px solid #e8e8e8' }}>{t('export.scope')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.statement.documents.map((doc, i) => (
                    <tr key={doc.doc_id} style={{ background: i % 2 === 0 ? 'white' : '#fafafa' }}>
                      <td style={{ padding: '0.5rem 0.75rem', borderBottom: '1px solid #f0f0f0', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                        {doc.filename}
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', borderBottom: '1px solid #f0f0f0', color: doc.status === 'granted' ? '#15803d' : '#b45309' }}>
                        {doc.status === 'granted' ? t('export.granted') : doc.status}
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', borderBottom: '1px solid #f0f0f0', color: '#555' }}>
                        {doc.scope || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Demonstrated Skills */}
          <div style={{ marginBottom: '2rem' }}>
            <h2 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: '0.75rem', color: '#1a1a1a' }}>
              {t('export.demonstratedSkills')}
            </h2>
            {demonstratedSkills.length === 0 ? (
              <p style={{ color: '#888', fontSize: '0.875rem', fontStyle: 'italic' }}>
                {t('export.noSkillsDemonstrated')}. {t('export.noSkillsDemonstratedDesc')}
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                {demonstratedSkills.map((skill, idx) => (
                  <div key={skill.skill_id} style={{
                    padding: '1rem 1.25rem',
                    border: '1px solid #e8e8e8',
                    borderRadius: '8px',
                    borderLeft: '4px solid var(--primary, #E18182)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                      <span style={{ fontWeight: 700, color: '#1a1a1a', fontSize: '0.9375rem' }}>
                        {idx + 1}. {skill.canonical_name}
                      </span>
                      <span style={{
                        padding: '0.125rem 0.5rem', borderRadius: '12px',
                        background: skill.label === 'demonstrated' ? '#dcfce7' : '#dbeafe',
                        color: skill.label === 'demonstrated' ? '#15803d' : '#1d4ed8',
                        fontSize: '0.75rem', fontWeight: 600,
                      }}>
                        {skill.label === 'demonstrated' ? t('export.demonstrated') : t('export.mentioned')}
                      </span>
                    </div>

                    {skill.rationale && (
                      <p style={{ fontSize: '0.875rem', color: '#444', margin: '0 0 0.75rem', fontStyle: 'italic' }}>
                        {skill.rationale}
                      </p>
                    )}

                    {skill.evidence_items.length > 0 && (
                      <div>
                        <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.375rem' }}>
                          {t('export.evidence')}
                        </div>
                        {skill.evidence_items.slice(0, 2).map((ev, i) => (
                          <div key={ev.chunk_id} style={{
                            marginBottom: '0.5rem',
                            padding: '0.5rem 0.75rem',
                            background: '#f8f8f8',
                            borderRadius: '4px',
                            fontSize: '0.8125rem',
                            color: '#333',
                            fontFamily: 'Georgia, serif',
                          }}>
                            <span style={{ color: '#888', fontSize: '0.7rem', display: 'block', marginBottom: '0.25rem' }}>
                              [{i + 1}] chunk:{ev.chunk_id.slice(0, 8)}
                              {ev.page_start != null && ` · p.${ev.page_start}`}
                              {ev.section_path && ` · §${ev.section_path}`}
                            </span>
                            &ldquo;{ev.snippet.slice(0, 200)}{ev.snippet.length > 200 ? '…' : ''}&rdquo;
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer / Attestation */}
          <div style={{
            borderTop: '1px solid #e8e8e8',
            paddingTop: '1.5rem',
            fontSize: '0.75rem',
            color: '#888',
            lineHeight: 1.6,
          }}>
            <p>
              This statement was automatically generated by SkillSight and reflects
              AI-assisted analysis of evidence documents provided by the student.
              All claims are traceable to audited evidence chunks with timestamps.
              Generated: {new Date(data.generated_at).toISOString()}
            </p>
            {data.verification_token && (
              <p style={{ marginTop: '0.5rem', wordBreak: 'break-all' }}>
                {t('export.verifyThisStatement')}: {typeof window !== 'undefined' ? `${window.location.origin}/export/verify?token=${encodeURIComponent(data.verification_token)}` : `[${t('export.verifyLink')}]`}
              </p>
            )}
            <p style={{ marginTop: '0.5rem' }}>
              © {new Date().getFullYear()} SkillSight · HKU Skills-to-Jobs Transparency System ·
              Audit ID available on request.
            </p>
          </div>
        </div>
      )}

      {/* Print styles */}
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: white; }
        }
      `}</style>
    </div>
  );
}
