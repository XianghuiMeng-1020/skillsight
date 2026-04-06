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

const DIMENSION_DESC_KEYS: Record<string, string> = {
  impact: 'resume.dimensionDescImpact',
  relevance: 'resume.dimensionDescRelevance',
  structure: 'resume.dimensionDescStructure',
  language: 'resume.dimensionDescLanguage',
  skills_presentation: 'resume.dimensionDescSkills',
  ats: 'resume.dimensionDescAts',
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
  const [retryTrigger, setRetryTrigger] = useState(0);

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
  }, [reviewId, retryTrigger, addToast]);

  if (loading || scoring) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step2Title')}</h2>
        <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>{t('resume.step2Desc')}</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span className="spinner" aria-hidden />
          <p style={{ color: 'var(--gray-500)', margin: 0 }}>{t('resume.scoring')}</p>
        </div>
      </>
    );
  }

  if (error || !scores) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step2Title')}</h2>
        <p style={{ color: 'var(--error)', marginBottom: '0.5rem' }}>{error || t('common.error')}</p>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setRetryTrigger((n) => n + 1)}>
          {t('common.retry')}
        </button>
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
      <p style={{ color: 'var(--gray-600)', marginBottom: '0.5rem' }}>{t('resume.step2Desc')}</p>
      <p style={{ fontSize: '0.8125rem', color: 'var(--gray-600)', marginBottom: '1rem' }}>{t('resume.atsFullName')}</p>
      <div style={{ marginBottom: '1.25rem', padding: '0.75rem 1rem', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)', background: 'var(--white)' }}>
        <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.78rem', lineHeight: 1.5, color: 'var(--gray-600)' }}>
          {DIMENSION_KEYS.map((key) => (
            <li key={key} style={{ marginBottom: '0.35rem' }}>
              <strong>{t(DIMENSION_LABEL_KEYS[key])}</strong>
              {' — '}
              {t(DIMENSION_DESC_KEYS[key])}
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.scoreRing} role="img" aria-label={t('resume.step2Title')}>
        <ResponsiveContainer width="100%" height={340}>
          <RechartsRadarChart data={radarData} margin={{ top: 30, right: 40, bottom: 30, left: 40 }}>
            <PolarGrid gridType="polygon" stroke="var(--gray-200)" />
            <PolarAngleAxis
              dataKey="labelKey"
              tickFormatter={(labelKey) => (typeof labelKey === 'string' ? t(labelKey) : String(labelKey))}
              tick={{ fontSize: 13, fontWeight: 600, fill: 'var(--gray-700)' }}
              tickLine={false}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: 'var(--gray-400)' }}
              axisLine={false}
              tickCount={5}
            />
            <Radar
              name={t('resume.totalScore')}
              dataKey="score"
              stroke={ringColor}
              fill={ringColor}
              fillOpacity={0.25}
              strokeWidth={2}
            />
            <Tooltip
              content={({ payload }) =>
                payload?.[0] ? (
                  <div style={{ background: '#fff', border: '1px solid var(--gray-200)', borderRadius: 8, padding: '6px 12px', fontSize: '0.85rem', fontWeight: 600, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                    {t(DIMENSION_LABEL_KEYS[payload[0].payload.dimension] || payload[0].payload.dimension)}: {fmt2(Number(payload[0].value))}
                  </div>
                ) : null
              }
            />
          </RechartsRadarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ fontSize: '0.78rem', color: 'var(--gray-600)', marginBottom: '1rem' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {DIMENSION_KEYS.map((key) => (
              <tr key={`radar-${key}`}>
                <td style={{ padding: '2px 0' }}>{t(DIMENSION_LABEL_KEYS[key] || key)}</td>
                <td style={{ textAlign: 'right', padding: '2px 0', fontWeight: 600 }}>{fmt2(scores[key]?.score ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.scoreRingValue} style={{ color: ringColor, marginBottom: '1.5rem' }}>
        {t('resume.totalScore')}: {fmt2(totalNum)}/100
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
                <span style={{ fontWeight: 600 }}>{fmt2(score)}</span>
              </div>
              <div className={styles.dimensionBar}>
                <div
                  className={styles.dimensionBarFill}
                  style={{ width: `${Math.min(100, Math.max(0, score))}%`, background: fillColor }}
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
