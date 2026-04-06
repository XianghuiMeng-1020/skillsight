'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';
import { studentBff } from '@/lib/bffClient';
import styles from './resume.module.css';

export function ResumeReviewsFooter() {
  const { t } = useLanguage();
  const [items, setItems] = useState<Array<{ review_id: string; status?: string; created_at?: string }>>([]);

  useEffect(() => {
    (async () => {
      try {
        const res = await studentBff.getResumeReviews(5, 0);
        setItems(res.reviews || []);
      } catch {
        setItems([]);
      }
    })();
  }, []);

  if (!items.length) return null;

  return (
    <div className={styles.resumeHistory}>
      <span className={styles.resumeHistoryLabel}>{t('resume.recentReviews')}</span>
      <ul className={styles.resumeHistoryList}>
        {items.map((r) => (
          <li key={r.review_id}>
            <Link href={`/dashboard/resume?review_id=${encodeURIComponent(r.review_id)}`} className={styles.resumeHistoryLink}>
              {r.review_id.slice(0, 8)}…{r.status ? ` · ${r.status}` : ''}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
