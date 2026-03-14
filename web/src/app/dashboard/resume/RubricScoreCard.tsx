'use client';

import { useEffect, useState } from 'react';
import {
  Radar,
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
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

interface RubricScoreCardProps {
  reviewId: string;
  onDone: (scores: Record<string, { score: number; comment: string }>, total: number) => void;
}

export function RubricScoreCard({ reviewId, onDone }: RubricScoreCardProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [scoring, setScoring] = useState(false);
  const [scores, setScores] = useState<Record<string, { score: number; comment: string }> | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setScoring(true);
      setError(null);
      try {
        const res = await studentBff.resumeReviewScore(reviewId);
        const initial = res.initial_scores ?? null;
        const tot = res.total_initial ?? 0;
        setScores(initial || null);
        setTotal(tot);
      } catch (e: unknown) {
        const err = e && typeof e === 'object' && 'message' in e ? String((e as { message: string }).message) : 'Scoring failed';
        setError(err);
        addToast('error', err);
      } finally {
        setScoring(false);
        setLoading(false);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only trigger score once per reviewId
  }, [reviewId]);

  if (loading || scoring) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step2Title')}</h2>
        <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>{t('resume.step2Desc')}</p>
        <p style={{ color: 'var(--gray-500)' }}>{t('resume.scoring')}</p>
      </>
    );
  }

  if (error || !scores) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step2Title')}</h2>
        <p style={{ color: 'var(--error)' }}>{error || t('common.error')}</p>
      </>
    );
  }

  const radarData = DIMENSION_KEYS.map((key) => ({
    dimension: key,
    fullMark: 100,
    score: scores[key]?.score ?? 0,
    labelKey: DIMENSION_LABEL_KEYS[key] || key,
  }));

  const totalNum = total ?? 0;
  const ringColor = totalNum < 60 ? 'var(--error)' : totalNum < 80 ? 'var(--warning)' : 'var(--success)';

  return (
    <>
      <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step2Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>{t('resume.step2Desc')}</p>

      <div className={styles.scoreRing}>
        <ResponsiveContainer width="100%" height={140}>
          <RechartsRadarChart data={radarData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
            <PolarGrid />
            <PolarAngleAxis
              dataKey="labelKey"
              tickFormatter={(labelKey) => (typeof labelKey === 'string' ? t(labelKey) : String(labelKey))}
            />
            <PolarRadiusAxis angle={90} domain={[0, 100]} />
            <Radar
              name={t('resume.totalScore')}
              dataKey="score"
              stroke={ringColor}
              fill={ringColor}
              fillOpacity={0.3}
            />
            <Tooltip
              content={({ payload }) =>
                payload?.[0] ? (
                  <span>
                    {t(DIMENSION_LABEL_KEYS[payload[0].payload.dimension] || payload[0].payload.dimension)}: {payload[0].value}
                  </span>
                ) : null
              }
            />
          </RechartsRadarChart>
        </ResponsiveContainer>
      </div>
      <p className={styles.scoreRingValue} style={{ color: ringColor, marginBottom: '1.5rem' }}>
        {t('resume.totalScore')}: {Math.round(totalNum)}/100
      </p>

      <div>
        {DIMENSION_KEYS.map((key) => {
          const d = scores[key];
          const score = d?.score ?? 0;
          const comment = d?.comment ?? '';
          const fillColor = score < 60 ? 'var(--error)' : score < 80 ? 'var(--warning)' : 'var(--success)';
          return (
            <div key={key} className={styles.dimensionCard}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                <span style={{ fontWeight: 600 }}>{t(DIMENSION_LABEL_KEYS[key] || key)}</span>
                <span style={{ fontWeight: 600 }}>{score}</span>
              </div>
              <div className={styles.dimensionBar}>
                <div
                  className={styles.dimensionBarFill}
                  style={{ width: `${score}%`, background: fillColor }}
                />
              </div>
              {comment && <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--gray-600)' }}>{comment}</p>}
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: '1.5rem' }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => scores && total != null && onDone(scores, total)}
        >
          {t('resume.nextStep')}
        </button>
      </div>
    </>
  );
}
