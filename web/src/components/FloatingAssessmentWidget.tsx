'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { AgentChat } from '@/components/AgentChat';
import { useAssessmentWidget } from '@/lib/AssessmentWidgetContext';
import { useLanguage } from '@/lib/contexts';
import styles from './FloatingAssessmentWidget.module.css';

const DEFAULT_SKILL_ID = 'HKU.SKILL.COMMUNICATION.v1';
const PROACTIVE_NUDGE_INTERVAL_MS = 2 * 60 * 1000;

export function FloatingAssessmentWidget() {
  const ctx = useAssessmentWidget();
  const { t } = useLanguage();
  const pathname = usePathname();
  const [hasBeenOpened, setHasBeenOpened] = useState(false);
  const [proactiveSnoozeUntil, setProactiveSnoozeUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  const handleOpen = useCallback(() => {
    setHasBeenOpened(true);
    setProactiveSnoozeUntil(Date.now() + PROACTIVE_NUDGE_INTERVAL_MS);
    setNow(Date.now());
    ctx?.openWidget();
  }, [ctx]);

  const handleClose = useCallback(() => {
    ctx?.closeWidget();
  }, [ctx]);

  const handleComplete = useCallback(
    (assessment?: { level: number; evidence_chunk_ids: string[]; why?: string }) => {
      if (assessment) ctx?.onAssessmentComplete?.(assessment);
      ctx?.closeWidget();
    },
    [ctx]
  );

  if (!ctx) return null;

  const isLoginPage = pathname === '/login';
  const skillId = ctx.skillId || DEFAULT_SKILL_ID;
  const skillName = ctx.skillName ?? undefined;
  const title =
    ctx.assessmentType != null
      ? `${ctx.assessmentType.replace(/_/g, ' ')} — AI Assessment`
      : (t('skills.tutorTitle') as string);

  const hasContext = ctx.assessmentType != null && ctx.skillId != null;
  const showChat = hasBeenOpened && (hasContext || true);
  const showLoginPrompt = isLoginPage && ctx.isOpen;
  const proactiveEligible =
    pathname.startsWith('/dashboard') &&
    !isLoginPage &&
    hasContext &&
    !ctx.isOpen;

  const shouldShowProactiveNudge = proactiveEligible && now >= proactiveSnoozeUntil;

  useEffect(() => {
    setProactiveSnoozeUntil(0);
    setNow(Date.now());
  }, [ctx.skillId, pathname]);

  useEffect(() => {
    if (!proactiveEligible || now >= proactiveSnoozeUntil) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [proactiveEligible, proactiveSnoozeUntil, now]);

  return (
    <>
      {shouldShowProactiveNudge && (
        <div className={styles.proactiveBubble} role="status" aria-live="polite">
          <button
            type="button"
            className={styles.proactiveClose}
            onClick={() => {
              setProactiveSnoozeUntil(Date.now() + PROACTIVE_NUDGE_INTERVAL_MS);
              setNow(Date.now());
            }}
            aria-label={t('common.close')}
          >
            ×
          </button>
          <div className={styles.proactiveTitle}>🤖 {t('dashboard.potentialAgentPromptTitle')}</div>
          <p className={styles.proactiveText}>{t('dashboard.potentialAgentPromptBody')}</p>
          <button type="button" className={styles.proactiveCta} onClick={handleOpen}>
            {t('dashboard.askAgentToPlan')}
          </button>
        </div>
      )}

      <button
        type="button"
        className={styles.fab}
        onClick={ctx.isOpen ? ctx.closeWidget : handleOpen}
        aria-label={ctx.isOpen ? t('assistant.closeWidget') : t('assistant.openWidget')}
        aria-expanded={ctx.isOpen}
      >
        <span className={styles.fabIcon}>🤖</span>
        <span className={styles.fabPulse} aria-hidden />
      </button>

      <div
        className={`${styles.panel} ${ctx.isOpen ? styles.panelOpen : ''}`}
        role="dialog"
        aria-label={t('assistant.widgetTitle')}
        aria-hidden={!ctx.isOpen}
      >
        <div className={styles.panelInner}>
          {showLoginPrompt ? (
            <div className={styles.loginPrompt}>
              <p>{t('assistant.loginRequired')}</p>
              <button type="button" className={styles.loginPromptBtn} onClick={handleClose}>
                {t('assistant.goLogin')}
              </button>
            </div>
          ) : showChat ? (
            <div className={styles.chatWrapper}>
              {!hasContext && (
                <div className={styles.contextHint}>
                  <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>🤖</div>
                  <p style={{ fontWeight: 500, marginBottom: '0.5rem' }}>{t('agent.noContextHint') as string}</p>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center', marginBottom: '0.75rem' }}>
                    <Link href="/dashboard/assessments" style={{ padding: '0.375rem 0.75rem', background: 'var(--coral-light, #fecdd3)', borderRadius: '8px', fontSize: '0.8125rem', textDecoration: 'none', color: 'var(--gray-800)' }}>
                      🎙️ {t('assess.communication')}
                    </Link>
                    <Link href="/dashboard/assessments" style={{ padding: '0.375rem 0.75rem', background: 'var(--sage-light, #d4e6da)', borderRadius: '8px', fontSize: '0.8125rem', textDecoration: 'none', color: 'var(--gray-800)' }}>
                      💻 {t('assess.programming')}
                    </Link>
                    <Link href="/dashboard/assessments" style={{ padding: '0.375rem 0.75rem', background: 'var(--peach-light, #fde8c8)', borderRadius: '8px', fontSize: '0.8125rem', textDecoration: 'none', color: 'var(--gray-800)' }}>
                      ✍️ {t('assess.writing')}
                    </Link>
                  </div>
                  <Link href="/dashboard/assessments" className={styles.contextHintLink}>
                    {t('agent.noContextLink') as string} →
                  </Link>
                </div>
              )}
              <AgentChat
                key={skillId}
                mode="assessment"
                skillId={skillId}
                skillName={skillName}
                title={title}
                onClose={handleClose}
                onComplete={handleComplete}
                embedded
              />
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
