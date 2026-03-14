'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { useLanguage } from '@/lib/contexts';
import { getToken } from '@/lib/bffClient';
import { ResumeUploader } from './ResumeUploader';
import { RubricScoreCard } from './RubricScoreCard';
import { SuggestionPanel } from './SuggestionPanel';
import { ScoreComparison } from './ScoreComparison';
import { TemplateGallery } from './TemplateGallery';
import styles from './resume.module.css';

const STEPS = [
  { key: 'step1Title', keyDesc: 'step1Desc' },
  { key: 'step2Title', keyDesc: 'step2Desc' },
  { key: 'step3Title', keyDesc: 'step3Desc' },
  { key: 'step4Title', keyDesc: 'step4Desc' },
  { key: 'step5Title', keyDesc: 'step5Desc' },
] as const;

export default function ResumePage() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const [step, setStep] = useState(1);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [docId, setDocId] = useState<string | null>(null);
  const [targetRoleId, setTargetRoleId] = useState<string | undefined>(undefined);
  const [initialScores, setInitialScores] = useState<Record<string, { score: number; comment: string }> | null>(null);
  const [finalScores, setFinalScores] = useState<Record<string, { score: number; comment: string }> | null>(null);
  const [totalInitial, setTotalInitial] = useState<number | null>(null);
  const [totalFinal, setTotalFinal] = useState<number | null>(null);
  const [suggestionsLoaded, setSuggestionsLoaded] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) {
      window.location.href = '/login';
    }
  }, []);

  const reviewIdFromUrl = searchParams.get('review_id');
  useEffect(() => {
    if (reviewIdFromUrl && !reviewId) {
      setReviewId(reviewIdFromUrl);
      setStep(2);
    }
  }, [reviewIdFromUrl, reviewId]);

  const handleStartReview = (id: string, doc: string, roleId?: string) => {
    setReviewId(id);
    setDocId(doc);
    setTargetRoleId(roleId);
    setStep(2);
  };

  const handleScoreDone = (scores: Record<string, { score: number; comment: string }>, total: number) => {
    setInitialScores(scores);
    setTotalInitial(total);
    setStep(3);
    setSuggestionsLoaded(false);
  };

  const handleSuggestionsDone = () => {
    setSuggestionsLoaded(true);
  };

  const handleContinueToComparison = () => setStep(4);

  const handleRescoreDone = (scores: Record<string, { score: number; comment: string }>, total: number) => {
    setFinalScores(scores);
    setTotalFinal(total);
  };

  const handleContinueToTemplates = () => setStep(5);

  return (
    <div className={styles.layout}>
      <Sidebar />
      <main className={styles.main}>
        <header className={styles.header}>
          <h1 className={styles.pageTitle}>{t('resume.pageTitle')}</h1>
          <nav className={styles.stepNav} role="list" aria-label="Steps">
            {STEPS.map((s, i) => {
              const stepNum = i + 1;
              const isCurrent = step === stepNum;
              const isDone = step > stepNum;
              return (
                <button
                  key={stepNum}
                  type="button"
                  className={`${styles.stepDot} ${isCurrent ? styles.stepDotCurrent : ''} ${isDone ? styles.stepDotDone : ''}`}
                  onClick={() => isDone && setStep(stepNum)}
                  aria-current={isCurrent ? 'step' : undefined}
                  aria-label={`${t(STEPS[i].key)}`}
                >
                  {isDone ? '✓' : stepNum}
                </button>
              );
            })}
          </nav>
        </header>

        <div className={styles.stepContent}>
          {step === 1 && (
            <ResumeUploader
              onStart={handleStartReview}
              existingReviewId={reviewId}
            />
          )}
          {step === 2 && reviewId && (
            <RubricScoreCard
              reviewId={reviewId}
              onDone={handleScoreDone}
            />
          )}
          {step === 3 && reviewId && (
            <SuggestionPanel
              reviewId={reviewId}
              onContinue={handleContinueToComparison}
              onSuggestionsLoaded={handleSuggestionsDone}
            />
          )}
          {step === 4 && reviewId && initialScores && (
            <ScoreComparison
              reviewId={reviewId}
              initialScores={initialScores}
              totalInitial={totalInitial ?? 0}
              onDone={handleRescoreDone}
              onContinue={handleContinueToTemplates}
            />
          )}
          {step === 5 && reviewId && (
            <TemplateGallery reviewId={reviewId} />
          )}
        </div>

        {step > 1 && step < 5 && (
          <div className={styles.backLink}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setStep(s => Math.max(1, s - 1))}
            >
              ← {t('common.back') || 'Back'}
            </button>
          </div>
        )}
        <div className={styles.footer}>
          <Link href="/dashboard" className="btn btn-ghost btn-sm">
            {t('nav.dashboard')}
          </Link>
          <Link href="/dashboard/change-log" className="btn btn-ghost btn-sm">
            {t('resume.viewHistory')}
          </Link>
        </div>
      </main>
    </div>
  );
}
