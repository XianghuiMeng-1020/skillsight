'use client';

import { Suspense, useEffect, useState } from 'react';
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
import { ResumeStepErrorBoundary } from './ResumeStepErrorBoundary';
import styles from './resume.module.css';

const STEPS = [
  { key: 'resume.step1Title', keyDesc: 'resume.step1Desc' },
  { key: 'resume.step2Title', keyDesc: 'resume.step2Desc' },
  { key: 'resume.step3Title', keyDesc: 'resume.step3Desc' },
  { key: 'resume.step4Title', keyDesc: 'resume.step4Desc' },
  { key: 'resume.step5Title', keyDesc: 'resume.step5Desc' },
] as const;

function ResumePageContent() {
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

  const handleBack = () => {
    const next = Math.max(1, step - 1);
    setStep(next);
    if (next === 1) {
      setReviewId(null);
      setDocId(null);
      setTargetRoleId(undefined);
      setInitialScores(null);
      setFinalScores(null);
      setTotalInitial(null);
      setTotalFinal(null);
      setSuggestionsLoaded(false);
    }
  };

  const sidebarOffset = { marginLeft: 'var(--sidebar-width, 260px)', position: 'relative' as const, zIndex: 1 };

  return (
    <div className={styles.layout}>
      <Sidebar />
      <main className={styles.main} style={sidebarOffset}>
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
          <ResumeStepErrorBoundary retryLabel={t('common.retry')}>
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
          </ResumeStepErrorBoundary>
        </div>

        {step > 1 && (
          <div className={styles.backLink}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={handleBack}
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

export default function ResumePage() {
  const { t } = useLanguage();
  return (
    <Suspense fallback={
      <div className={styles.layout}>
        <Sidebar />
        <main className={styles.main} style={{ marginLeft: 'var(--sidebar-width, 260px)', position: 'relative', zIndex: 1 }}>
          <p>{t('common.loading')}</p>
        </main>
      </div>
    }>
      <ResumePageContent />
    </Suspense>
  );
}
