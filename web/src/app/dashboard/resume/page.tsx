'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { useLanguage } from '@/lib/contexts';
import { getToken, studentBff } from '@/lib/bffClient';
import { ResumeUploader } from './ResumeUploader';
import { RubricScoreCard } from './RubricScoreCard';
import { SuggestionPanel } from './SuggestionPanel';
import { ScoreComparison } from './ScoreComparison';
import { TemplateGallery } from './TemplateGallery';
import { ResumeStepErrorBoundary } from './ResumeStepErrorBoundary';
import { LayoutHealthPanel } from './LayoutHealthPanel';
import { ResumeReviewsFooter } from './ResumeReviewsFooter';
import { ResumeWorkbench } from './ResumeWorkbench';
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
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initialReviewId = searchParams.get('review_id');
  const initialStepRaw = Number(searchParams.get('step') || (initialReviewId ? '2' : '1'));
  const initialStep = Number.isFinite(initialStepRaw) ? Math.min(5, Math.max(initialReviewId ? 2 : 1, initialStepRaw)) : 1;
  const [step, setStep] = useState(initialStep);
  const [reviewId, setReviewId] = useState<string | null>(initialReviewId);
  const [initialScores, setInitialScores] = useState<Record<string, { score: number; comment: string }> | null>(null);
  const [totalInitial, setTotalInitial] = useState<number | null>(null);
  const [resumeOverrideText, setResumeOverrideText] = useState('');
  const [templateOptions, setTemplateOptions] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) {
      window.location.href = '/login';
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (reviewId) {
      params.set('review_id', reviewId);
      params.set('step', String(step));
    } else {
      params.delete('review_id');
      params.delete('step');
    }
    const q = params.toString();
    router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
  }, [reviewId, step, pathname, router]);

  const [maxReachableStep, setMaxReachableStep] = useState<number>(5);
  useEffect(() => {
    if (!reviewId) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await studentBff.resumeReviewState(reviewId);
        if (cancelled) return;
        const safeMax = Math.min(5, Math.max(1, Number(st.max_step || 1)));
        setMaxReachableStep(safeMax);
        setStep((prev) => {
          if (prev > safeMax) return safeMax;
          if (prev < 2) return 2;
          return prev;
        });
      } catch {
        // Keep current UI state; backend still enforces invalid_state.
      }
    })();
    return () => {
      cancelled = true;
    };
  // Only validate on initial load / reviewId change, NOT on every step change
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId]);

  const handleStartReview = (id: string) => {
    setReviewId(id);
    setStep(2);
  };

  const advanceStep = useCallback((target: number) => {
    setMaxReachableStep((prev) => Math.max(prev, target));
    setStep(target);
  }, []);

  const handleScoreDone = (scores: Record<string, { score: number; comment: string }>, total: number) => {
    setInitialScores(scores);
    setTotalInitial(total);
    advanceStep(3);
  };

  const handleContinueToComparison = () => advanceStep(4);

  const handleRescoreDone = () => {};

  const handleContinueToTemplates = () => advanceStep(5);

  const handleBack = () => {
    const next = Math.max(1, step - 1);
    setStep(next);
    if (next === 1) {
      setReviewId(null);
      setInitialScores(null);
      setTotalInitial(null);
      setResumeOverrideText('');
      setTemplateOptions({});
    }
  };

  const handleOverrideChange = useCallback((text: string) => {
    setResumeOverrideText(text);
  }, []);

  const handleTemplateOptionsChange = useCallback((opts: Record<string, unknown>) => {
    setTemplateOptions(opts);
  }, []);

  return (
    <div className={styles.layout}>
      <Sidebar />
      <main className={styles.main}>
        <header className={styles.header}>
          <h1 className={styles.pageTitle}>{t('resume.pageTitle')}</h1>
          <p className={styles.disclaimer} role="note">
            {t('resume.disclaimer')}
          </p>
          <nav className={styles.stepNav} aria-label={t('resume.pageTitle')}>
            <ol className={styles.stepNavList}>
              {STEPS.map((s, i) => {
                const stepNum = i + 1;
                const isCurrent = step === stepNum;
                const isDone = step > stepNum;
                return (
                  <li key={stepNum}>
                    <button
                      type="button"
                      className={`${styles.stepDot} ${isCurrent ? styles.stepDotCurrent : ''} ${isDone ? styles.stepDotDone : ''}`}
                      onClick={() => isDone && setStep(stepNum)}
                      disabled={!isDone && !isCurrent}
                      aria-disabled={!isDone && !isCurrent}
                      aria-current={isCurrent ? 'step' : undefined}
                      aria-label={`${stepNum}. ${t(STEPS[i].key)}`}
                    >
                      {isDone ? '✓' : stepNum}
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
          <p className={styles.stepNavCaption}>
            <strong>{t(STEPS[step - 1].key)}</strong>
            {' — '}
            {t(STEPS[step - 1].keyDesc)}
          </p>
        </header>

        <div className={styles.stepContent}>
          <ResumeStepErrorBoundary retryLabel={t('common.retry')}>
            {step === 1 && (
              <ResumeUploader
                onStart={handleStartReview}
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
              <>
                <LayoutHealthPanel reviewId={reviewId} />
                <p className={styles.exportWpsNote}>{t('resume.exportWpsNote')}</p>
                <ResumeWorkbench
                  reviewId={reviewId}
                  onResumeOverrideChange={handleOverrideChange}
                  onTemplateOptionsChange={handleTemplateOptionsChange}
                />
                <TemplateGallery
                  reviewId={reviewId}
                  resumeOverrideText={resumeOverrideText}
                  templateOptions={templateOptions}
                />
              </>
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
          <ResumeReviewsFooter />
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
        <main className={styles.main}>
          <p>{t('common.loading')}</p>
        </main>
      </div>
    }>
      <ResumePageContent />
    </Suspense>
  );
}
