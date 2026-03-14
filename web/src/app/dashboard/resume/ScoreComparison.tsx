'use client';

import { useEffect, useState } from 'react';
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

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await studentBff.resumeReviewRescore(reviewId);
        setFinalScores(res.final_scores ?? null);
        setTotalFinal(res.total_final ?? null);
        if (res.final_scores && res.total_final != null) {
          onDone(res.final_scores, res.total_final);
        }
      } catch (e: unknown) {
        const err = e && typeof e === 'object' && 'message' in e ? String((e as { message: string }).message) : 'Rescore failed';
        setError(err);
        addToast('error', err);
      } finally {
        setLoading(false);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per reviewId
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

      <div className={styles.scoreRing} style={{ marginBottom: '1rem' }}>
        <ResponsiveContainer width="100%" height={180}>
          <RechartsRadarChart data={radarData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
            <PolarGrid />
            <PolarAngleAxis
              dataKey="labelKey"
              tickFormatter={(labelKey) => (typeof labelKey === 'string' ? t(labelKey) : String(labelKey))}
            />
            <PolarRadiusAxis angle={90} domain={[0, 100]} />
            <Radar
              name={t('resume.beforeScore')}
              dataKey="initial"
              stroke="var(--gray-400)"
              fill="var(--gray-400)"
              fillOpacity={0.2}
              strokeDasharray="4 4"
            />
            <Radar
              name={t('resume.afterScore')}
              dataKey="final"
              stroke="var(--primary)"
              fill="var(--primary)"
              fillOpacity={0.3}
            />
            <Tooltip
              content={({ payload }) =>
                payload?.[0] ? (
                  <span>
                    {t(DIMENSION_LABEL_KEYS[payload[0].payload.dimension] || payload[0].payload.dimension)}: {t('resume.beforeScore')} {payload[0].payload.initial}, {t('resume.afterScore')} {payload[0].payload.final}
                  </span>
                ) : null
              }
            />
            <Legend />
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

      {improved && (
        <p style={{ color: 'var(--success)', fontWeight: 600, marginBottom: '1rem' }}>
          {t('resume.improvement')?.replace('{n}', String(delta)) ?? `+${delta} points`}
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
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <div className={styles.dimensionBar} style={{ flex: 1 }}>
                  <div
                    className={styles.dimensionBarFill}
                    style={{ width: `${init}%`, background: 'var(--gray-300)' }}
                  />
                </div>
                <div className={styles.dimensionBar} style={{ flex: 1 }}>
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
