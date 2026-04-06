'use client';

import { useEffect, useState } from 'react';
import { useLanguage } from '@/lib/contexts';
import { studentBff } from '@/lib/bffClient';
import styles from './resume.module.css';

export function LayoutHealthPanel({ reviewId }: { reviewId: string }) {
  const { t } = useLanguage();
  const [score, setScore] = useState<number | null>(null);
  const [issues, setIssues] = useState<Array<{ level: string; code: string; message: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const res = await studentBff.resumeReviewLayoutCheck(reviewId);
        if (!cancelled) {
          setScore(res.score);
          setIssues(res.issues || []);
        }
      } catch (e: unknown) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reviewId]);

  if (loading) {
    return (
      <div className={styles.layoutHealth} aria-busy="true">
        <div className={styles.layoutHealthSkeleton} />
      </div>
    );
  }
  if (err) {
    return null;
  }

  return (
    <div className={styles.layoutHealth}>
      <div className={styles.layoutHealthHeader}>
        <span className={styles.layoutHealthTitle}>{t('resume.layoutHealthTitle')}</span>
        {score !== null && (
          <span className={styles.layoutHealthScore} title={t('resume.layoutHealthScoreHint')}>
            {score}/100
          </span>
        )}
      </div>
      {issues.length === 0 ? (
        <p className={styles.layoutHealthOk}>{t('resume.layoutHealthOk')}</p>
      ) : (
        <ul className={styles.layoutHealthList}>
          {issues.map((it, i) => (
            <li key={`${it.code}-${i}`} data-level={it.level}>
              {it.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
