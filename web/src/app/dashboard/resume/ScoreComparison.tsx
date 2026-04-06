'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Radar,
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from 'recharts';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { studentBff } from '@/lib/bffClient';
import { fmt2 } from '@/lib/formatNumber';
import styles from './resume.module.css';

const DIMENSION_KEYS = ['impact', 'relevance', 'structure', 'language', 'skills_presentation', 'ats'] as const;
const DIMENSION_LABEL_KEYS: Record<string, string> = {
  impact: 'resume.dimensionImpact',
  relevance: 'resume.dimensionRelevance',
  structure: 'resume.dimensionStructure',
  language: 'resume.dimensionLanguage',
  skills_presentation: 'resume.dimensionSkills',
  ats: 'resume.dimensionAts',
};

interface ScoreComparisonProps {
  reviewId: string;
  initialScores: Record<string, { score: number; comment: string }>;
  totalInitial: number;
  onDone: (finalScores: Record<string, { score: number; comment: string }>, totalFinal: number) => void;
  onContinue: () => void;
}

export function ScoreComparison({
  reviewId,
  initialScores,
  totalInitial,
  onDone,
  onContinue,
}: ScoreComparisonProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [finalScores, setFinalScores] = useState<Record<string, { score: number; comment: string }> | null>(null);
  const [totalFinal, setTotalFinal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryTrigger, setRetryTrigger] = useState(0);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await studentBff.resumeReviewRescore(reviewId);
        if (cancelled) return;
        setFinalScores(res.final_scores ?? null);
        setTotalFinal(res.total_final ?? null);
        if (res.final_scores && res.total_final != null) {
          onDoneRef.current(res.final_scores, res.total_final);
        }
      } catch (e: unknown) {
        if (cancelled) return;
        const err = e instanceof Error ? e.message : (e && typeof e === 'object' && 'message' in e ? String((e as { message: string }).message) : 'Rescore failed');
        setError(err);
        addToast('error', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [reviewId, retryTrigger, addToast]);

  if (loading) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step4Title')}</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span className="spinner" aria-hidden />
          <p style={{ color: 'var(--gray-600)', margin: 0 }}>{t('resume.rescoring')}</p>
        </div>
      </>
    );
  }

  if (error || !finalScores || totalFinal == null) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step4Title')}</h2>
        <p style={{ color: 'var(--error)', marginBottom: '0.75rem' }}>{error || t('common.error')}</p>
        <button type="button" className="btn btn-primary" onClick={() => setRetryTrigger((n) => n + 1)}>
          {t('resume.retryRescore')}
        </button>
      </>
    );
  }

  const radarData = DIMENSION_KEYS.map((key) => ({
    dimension: key,
    fullMark: 100,
    initial: initialScores[key]?.score ?? 0,
    final: finalScores[key]?.score ?? 0,
    labelKey: DIMENSION_LABEL_KEYS[key] || key,
  }));

  const delta = Math.round((totalFinal - totalInitial) * 100) / 100;
  const improved = delta > 0;

  return (
    <>
      <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step4Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '0.5rem' }}>{t('resume.step4Desc')}</p>
      <p style={{ fontSize: '0.8125rem', color: 'var(--gray-500)', marginBottom: '1rem', lineHeight: 1.45 }}>{t('resume.step4RadarLineLegend')}</p>

      <div className={styles.scoreRing} style={{ marginBottom: '1rem', height: 320 }} role="img" aria-label={t('resume.step4Title')}>
        <ResponsiveContainer width="100%" height={320}>
          <RechartsRadarChart data={radarData} margin={{ top: 20, right: 30, bottom: 20, left: 30 }}>
            <PolarGrid gridType="polygon" stroke="var(--gray-200)" />
            <PolarAngleAxis
              dataKey="labelKey"
              tickFormatter={(labelKey) => (typeof labelKey === 'string' ? t(labelKey) : String(labelKey))}
              tick={{ fontSize: 12, fill: 'var(--gray-600)' }}
            />
            <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
            <Radar
              name={t('resume.beforeScore')}
              dataKey="initial"
              stroke="var(--gray-400)"
              fill="var(--gray-400)"
              fillOpacity={0.15}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 3, fill: 'var(--gray-400)' }}
            />
            <Radar
              name={t('resume.afterScore')}
              dataKey="final"
              stroke="var(--primary)"
              fill="var(--primary)"
              fillOpacity={0.25}
              strokeWidth={2.5}
              dot={{ r: 4, fill: 'var(--primary)' }}
            />
            <Tooltip
              content={({ payload }) =>
                payload?.[0] ? (
                  <div style={{
                    background: 'var(--white)',
                    border: '1px solid var(--gray-200)',
                    borderRadius: 'var(--radius)',
                    padding: '0.5rem 0.75rem',
                    fontSize: '0.825rem',
                    boxShadow: 'var(--shadow)',
                  }}>
                    <strong>{t(DIMENSION_LABEL_KEYS[payload[0].payload.dimension] || payload[0].payload.dimension)}</strong>
                    <div style={{ display: 'flex', gap: '1rem', marginTop: '0.25rem' }}>
                      <span style={{ color: 'var(--gray-400)' }}>{t('resume.beforeScore')}: {fmt2(Number(payload[0].payload.initial))}</span>
                      <span style={{ color: 'var(--primary)', fontWeight: 600 }}>{t('resume.afterScore')}: {fmt2(Number(payload[0].payload.final))}</span>
                      {payload[0].payload.final - payload[0].payload.initial !== 0 && (
                        <span style={{ color: payload[0].payload.final > payload[0].payload.initial ? 'var(--success)' : 'var(--error)', fontWeight: 600 }}>
                          {payload[0].payload.final > payload[0].payload.initial ? '+' : ''}{fmt2(Math.round((payload[0].payload.final - payload[0].payload.initial) * 100) / 100)}
                        </span>
                      )}
                    </div>
                  </div>
                ) : null
              }
            />
            <Legend
              wrapperStyle={{ paddingTop: '0.5rem', fontSize: '0.825rem' }}
              formatter={(value: string) => <span style={{ color: 'var(--gray-700)' }}>{value}</span>}
            />
          </RechartsRadarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ fontSize: '0.78rem', color: 'var(--gray-600)', marginBottom: '1rem' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {DIMENSION_KEYS.map((key) => (
              <tr key={`cmp-${key}`}>
                <td style={{ padding: '2px 0' }}>{t(DIMENSION_LABEL_KEYS[key] || key)}</td>
                <td style={{ textAlign: 'right', padding: '2px 0' }}>
                  {fmt2(initialScores[key]?.score ?? 0)} → <strong>{fmt2(finalScores[key]?.score ?? 0)}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.comparisonGrid}>
        <div style={{ textAlign: 'center', padding: '1rem', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('resume.beforeScore')}</p>
          <p style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700 }}>{fmt2(totalInitial)}</p>
        </div>
        <div style={{ textAlign: 'center', padding: '1rem', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('resume.afterScore')}</p>
          <p style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: improved ? 'var(--success)' : 'var(--gray-700)' }}>
            {fmt2(totalFinal)}
          </p>
        </div>
      </div>

      {Math.abs(delta) > 0.005 && (
        <p style={{ color: improved ? 'var(--success)' : 'var(--gray-600)', fontWeight: 600, marginBottom: '1rem' }}>
          {improved
            ? (t('resume.improvement')?.replace('{n}', fmt2(delta)) ?? `+${fmt2(delta)} points`)
            : (t('resume.scoreChange') ?? `Score change: ${fmt2(delta)} points`)}
        </p>
      )}

      <div>
        {DIMENSION_KEYS.map((key) => {
          const init = initialScores[key]?.score ?? 0;
          const fin = finalScores[key]?.score ?? 0;
          const dimLabel = t(DIMENSION_LABEL_KEYS[key] || key);
          return (
            <div key={key} className={styles.dimensionCard}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <span style={{ fontWeight: 600 }}>{dimLabel}</span>
                <span>
                  {fmt2(init)} → <strong style={{ color: fin >= init ? 'var(--success)' : 'var(--gray-700)' }}>{fmt2(fin)}</strong>
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }} role="group" aria-label={`${dimLabel}: ${t('resume.beforeScore')} ${init}, ${t('resume.afterScore')} ${fin}`}>
                <div className={styles.dimensionBar} style={{ flex: 1 }} role="progressbar" aria-valuenow={init} aria-valuemin={0} aria-valuemax={100} aria-label={`${dimLabel} ${t('resume.beforeScore')}`}>
                  <div
                    className={styles.dimensionBarFill}
                    style={{ width: `${Math.min(100, Math.max(0, init))}%`, background: 'var(--gray-300)' }}
                  />
                </div>
                <div className={styles.dimensionBar} style={{ flex: 1 }} role="progressbar" aria-valuenow={fin} aria-valuemin={0} aria-valuemax={100} aria-label={`${dimLabel} ${t('resume.afterScore')}`}>
                  <div
                    className={styles.dimensionBarFill}
                    style={{ width: `${Math.min(100, Math.max(0, fin))}%`, background: 'var(--primary)' }}
                  />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                <span>{t('resume.beforeScore')}</span>
                <span>{t('resume.afterScore')}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <button type="button" className="btn btn-primary" onClick={onContinue}>
          {t('resume.chooseTemplate')}
        </button>
      </div>
    </>
  );
}
