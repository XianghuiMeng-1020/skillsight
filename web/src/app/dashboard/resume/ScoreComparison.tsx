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
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await studentBff.resumeReviewRescore(reviewId);
        setFinalScores(res.final_scores ?? null);
        setTotalFinal(res.total_final ?? null);
        if (res.final_scores && res.total_final != null) {
          onDoneRef.current(res.final_scores, res.total_final);
        }
      } catch (e: unknown) {
        const err = e instanceof Error ? e.message : (e && typeof e === 'object' && 'message' in e ? String((e as { message: string }).message) : 'Rescore failed');
        setError(err);
        addToast('error', err);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [reviewId]);

  if (loading) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step4Title')}</h2>
        <p style={{ color: 'var(--gray-600)' }}>{t('resume.rescoring')}</p>
      </>
    );
  }

  if (error || !finalScores || totalFinal == null) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step4Title')}</h2>
        <p style={{ color: 'var(--error)' }}>{error || t('common.error')}</p>
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

  const delta = totalFinal - totalInitial;
  const improved = delta > 0;

  return (
    <>
      <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step4Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>{t('resume.step4Desc')}</p>

      <div className={styles.scoreRing} style={{ marginBottom: '1rem', height: 320 }}>
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
              stroke="#9ca3af"
              fill="#9ca3af"
              fillOpacity={0.15}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 3, fill: '#9ca3af' }}
            />
            <Radar
              name={t('resume.afterScore')}
              dataKey="final"
              stroke="#6366f1"
              fill="#6366f1"
              fillOpacity={0.25}
              strokeWidth={2.5}
              dot={{ r: 4, fill: '#6366f1' }}
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
                      <span style={{ color: '#9ca3af' }}>{t('resume.beforeScore')}: {payload[0].payload.initial}</span>
                      <span style={{ color: '#6366f1', fontWeight: 600 }}>{t('resume.afterScore')}: {payload[0].payload.final}</span>
                      {payload[0].payload.final - payload[0].payload.initial !== 0 && (
                        <span style={{ color: payload[0].payload.final > payload[0].payload.initial ? 'var(--success)' : 'var(--error)', fontWeight: 600 }}>
                          {payload[0].payload.final > payload[0].payload.initial ? '+' : ''}{payload[0].payload.final - payload[0].payload.initial}
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

      <div className={styles.comparisonGrid} style={{ gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        <div style={{ textAlign: 'center', padding: '1rem', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('resume.beforeScore')}</p>
          <p style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700 }}>{Math.round(totalInitial)}</p>
        </div>
        <div style={{ textAlign: 'center', padding: '1rem', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)' }}>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('resume.afterScore')}</p>
          <p style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: improved ? 'var(--success)' : 'var(--gray-700)' }}>
            {Math.round(totalFinal)}
          </p>
        </div>
      </div>

      {delta !== 0 && (
        <p style={{ color: improved ? 'var(--success)' : 'var(--gray-600)', fontWeight: 600, marginBottom: '1rem' }}>
          {improved
            ? (t('resume.improvement')?.replace('{n}', String(delta)) ?? `+${delta} points`)
            : (t('resume.scoreChange') ?? `Score change: ${delta} points`)}
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
                  {init} → <strong style={{ color: fin >= init ? 'var(--success)' : 'var(--gray-700)' }}>{fin}</strong>
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }} role="group" aria-label={`${dimLabel}: ${t('resume.beforeScore')} ${init}, ${t('resume.afterScore')} ${fin}`}>
                <div className={styles.dimensionBar} style={{ flex: 1 }} role="progressbar" aria-valuenow={init} aria-valuemin={0} aria-valuemax={100} aria-label={`${dimLabel} ${t('resume.beforeScore')}`}>
                  <div
                    className={styles.dimensionBarFill}
                    style={{ width: `${init}%`, background: 'var(--gray-300)' }}
                  />
                </div>
                <div className={styles.dimensionBar} style={{ flex: 1 }} role="progressbar" aria-valuenow={fin} aria-valuemin={0} aria-valuemax={100} aria-label={`${dimLabel} ${t('resume.afterScore')}`}>
                  <div
                    className={styles.dimensionBarFill}
                    style={{ width: `${fin}%`, background: 'var(--primary)' }}
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
