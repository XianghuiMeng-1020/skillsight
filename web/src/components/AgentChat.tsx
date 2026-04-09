'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { studentBff } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';
import { logger } from '@/lib/logger';
import styles from './AgentChat.module.css';

export type AgentChatMode = 'assessment' | 'resume_review';

export interface AgentChatProps {
  mode: AgentChatMode;
  skillId?: string;
  skillName?: string;
  title?: string;
  onClose: () => void;
  onComplete?: (assessment?: { level: number; evidence_chunk_ids: string[]; why?: string }) => void;
  docIds?: string[];
  embedded?: boolean;
}

const CAREER_URL = 'https://careers.hku.hk';
const MAX_TURNS_ASSESSMENT = 10;
const MAX_INPUT_LENGTH_ASSESSMENT = 500;

type Turn = { role: 'user' | 'assistant'; content: string; ts?: number };

function formatTime(ts: number, t: (k: string) => string): string {
  const diff = (Date.now() - ts) / 1000;
  if (diff < 60) return t('agent.justNow');
  if (diff < 120) return t('agent.minAgo');
  const mins = Math.floor(diff / 60);
  return `${mins} ${t('agent.minsAgo')}`;
}

function UserAvatar({ language }: { language: string }) {
  const letter = language.startsWith('zh') ? '我' : 'Y';
  return <span className={`${styles.avatar} ${styles.avatarUser}`}>{letter}</span>;
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M22 2L11 13" />
      <path d="M22 2L15 22L11 13L2 9L22 2Z" />
    </svg>
  );
}

export function AgentChat({
  mode,
  skillId = 'HKU.SKILL.COMMUNICATION.v1',
  skillName,
  title,
  onClose,
  onComplete,
  docIds,
  embedded = false,
}: AgentChatProps) {
  const { t, language } = useLanguage();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [concluded, setConcluded] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [sessionStarted, setSessionStarted] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [turns, loading, scrollToBottom]);

  const startSession = useCallback(async () => {
    setStartError(null);
    setLoading(true);
    try {
      const res = await studentBff.tutorSessionStart(skillId, docIds, mode);
      setSessionId(res.session_id);
      let greeting = (t('agent.greeting') as string)?.trim() || (t('agent.welcomeFallback') as string) || 'Hi! How can I help you today?';
      if (mode === 'assessment') {
        const turnLimitLine = (t('agent.turnLimitGreeting') as string) || '';
        if (turnLimitLine) greeting = `${greeting}\n\n${turnLimitLine}`;
      }
      setTurns([{ role: 'assistant', content: greeting, ts: Date.now() }]);
    } catch (e) {
      logger.error('AgentChat session start failed', e);
      const raw = e instanceof Error ? e.message : String(e);
      const isNetwork = /failed to fetch|network error|cors|load failed/i.test(raw) || raw === 'Failed to fetch';
      const errMsg = isNetwork ? (t('agent.sessionStartFailed') as string) : (t('agent.serviceUnavailable') as string) || (t('agent.sessionStartFailed') as string);
      setStartError(errMsg);
    } finally {
      setLoading(false);
    }
  }, [skillId, docIds, mode, t]);

  useEffect(() => {
    if (sessionStarted || loading || sessionId) return;
    setSessionStarted(true);
    startSession();
  }, [sessionStarted, loading, sessionId, startSession]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || !sessionId || loading || concluded) return;
    setInput('');
    const userTurn: Turn = { role: 'user', content: text, ts: Date.now() };
    setTurns((prev) => [...prev, userTurn]);
    setLoading(true);
    try {
      const res = await studentBff.tutorSessionMessage(sessionId, text);
      setTurns((prev) => [...prev, { role: 'assistant', content: res.reply, ts: Date.now() }]);
      if (res.concluded && res.assessment) {
        setConcluded(true);
        onComplete?.(res.assessment);
      }
    } catch (e) {
      logger.error('AgentChat message failed', e);
      setTurns((prev) => [
        ...prev,
        { role: 'assistant', content: (t('skills.tutorError') as string) || 'Sorry, something went wrong. Please try again.', ts: Date.now() },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, sessionId, loading, concluded, onComplete, t]);

  const userTurnCount = turns.filter((x) => x.role === 'user').length;
  const turnLimitReached = mode === 'assessment' && userTurnCount >= MAX_TURNS_ASSESSMENT && !concluded;

  const displayTitle =
    title ||
    (mode === 'resume_review'
      ? ((t('agent.resumeReview') as string) || 'Review My Resume')
      : ((t('skills.tutorTitle') as string) + (skillName ? ` — ${skillName}` : '')));

  const content = (
    <>
      <div className={`${styles.header} ${embedded ? styles.headerEmbedded : ''}`}>
        <span className={styles.titleRow}>
          <span className={`${styles.avatar} ${styles.avatarAgent}`}>🤖</span>
          {displayTitle}
          {loading && !sessionId && !startError && (
            <span className={styles.headerSpinner} aria-hidden />
          )}
          {mode === 'assessment' && sessionId && (
            <span className={styles.turnBadge} aria-label={`Turn ${userTurnCount} of ${MAX_TURNS_ASSESSMENT}`}>
              {userTurnCount}/{MAX_TURNS_ASSESSMENT}
            </span>
          )}
        </span>
        <button
          type="button"
          className={styles.headerCloseBtn}
          onClick={onClose}
          disabled={loading}
          aria-label={t('skills.tutorClose') as string}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className={`${styles.messages} ${embedded ? styles.messagesEmbedded : ''}`} role="log" aria-live="polite">
        {!sessionId && !startError && (
          <div className={styles.startBlock}>
            {loading ? (
              <>
                <span className={styles.spinner} />
                {t('skills.loading') as string}
                <div style={{ marginTop: '0.75rem', fontSize: '0.8125rem', color: 'var(--gray-400)' }}>
                  {t('skills.loadingSlowHint') as string}
                </div>
              </>
            ) : (
              <div style={{ marginTop: '0.5rem' }}>
                <span>{t('skills.loading') as string}</span>
                <button type="button" className={styles.retryBtn} style={{ marginLeft: '0.5rem' }} onClick={() => { setSessionStarted(false); }}>
                  {t('agent.retry') as string}
                </button>
              </div>
            )}
          </div>
        )}

        {startError && (
          <div className={styles.errorBlock} role="alert">
            <span>{startError}</span>
            <div className={styles.errorActions}>
              <button type="button" className={styles.retryBtn} onClick={() => { setStartError(null); setSessionStarted(false); }} aria-label={t('agent.retry') as string}>
                {t('agent.retry') as string}
              </button>
              <button type="button" className={styles.dismissBtn} onClick={onClose} aria-label={t('common.close') as string}>
                {t('common.close') as string}
              </button>
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div
            key={i}
            className={`${styles.row} ${turn.role === 'user' ? styles.rowUser : styles.rowAgent}`}
          >
            {turn.role === 'assistant' && <span className={`${styles.avatar} ${styles.avatarAgent}`}>🤖</span>}
            <div className={styles.bubbleWrap}>
              <div className={turn.role === 'user' ? styles.bubbleUser : styles.bubbleAgent}>
                {turn.content}
              </div>
              {turn.ts != null && (
                <div className={styles.timestamp}>{formatTime(turn.ts, t)}</div>
              )}
            </div>
            {turn.role === 'user' && <UserAvatar language={language} />}
          </div>
        ))}

        {loading && turns.some((x) => x.role === 'user') && (
          <div className={styles.typingWrap}>
            <span className={`${styles.avatar} ${styles.avatarAgent}`}>🤖</span>
            <div className={styles.typingBubble}>
              <span className={styles.typingDot} aria-hidden />
              <span className={styles.typingDot} aria-hidden />
              <span className={styles.typingDot} aria-hidden />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} aria-hidden />

        {concluded && mode === 'assessment' && (
          <p className={styles.concluded}>{t('skills.tutorConcluded') as string}</p>
        )}
      </div>

      {sessionId && (
        <>
          <div className={styles.careerBar}>
            <a href={CAREER_URL} target="_blank" rel="noopener noreferrer" className={styles.careerLink}>
              {t('agent.careerBar') as string}
            </a>
          </div>
          <div className={styles.inputArea}>
            {turnLimitReached && (
              <p className={styles.turnLimitHint}>
                {t('skills.tutorTurnLimit') as string}
              </p>
            )}
            {turnLimitReached && (
              <div style={{ marginBottom: '0.5rem', textAlign: 'center' }}>
                <button
                  type="button"
                  className={styles.endSessionBtn}
                  onClick={async () => {
                    if (!sessionId) return;
                    setLoading(true);
                    try {
                      await studentBff.tutorSessionEnd(sessionId);
                      setConcluded(true);
                      onComplete?.({ level: 0, evidence_chunk_ids: [], why: 'Session ended by user at turn limit' });
                    } catch {
                      setTurns((prev) => [
                        ...prev,
                        { role: 'assistant', content: (t('agent.endSessionFailed') as string) || 'Failed to end session. Please close and restart.', ts: Date.now() },
                      ]);
                    } finally {
                      setLoading(false);
                    }
                  }}
                  disabled={loading}
                >
                  {t('agent.endSession') as string}
                </button>
              </div>
            )}
            <div className={styles.inputRow}>
              <input
                type="text"
                className={styles.input}
                value={input}
                onChange={(e) =>
                  setInput(
                    mode === 'assessment'
                      ? e.target.value.slice(0, MAX_INPUT_LENGTH_ASSESSMENT)
                      : e.target.value
                  )
                }
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                placeholder={
                  mode === 'assessment'
                    ? ((t('skills.tutorPlaceholderAssessment') as string) || 'Reply about the assessment (brief)...')
                    : (t('skills.tutorPlaceholder') as string)
                }
                disabled={loading || concluded || turnLimitReached}
                maxLength={mode === 'assessment' ? MAX_INPUT_LENGTH_ASSESSMENT : undefined}
              />
              <button
                type="button"
                className={styles.sendBtn}
                onClick={sendMessage}
                disabled={!input.trim() || loading || concluded || turnLimitReached}
                aria-label={t('skills.tutorSend') as string}
              >
                {loading ? <span className={styles.spinner} /> : <SendIcon />}
              </button>
            </div>
            {mode === 'assessment' && (input.length > 0 || turnLimitReached) && (
              <div className={styles.charCount} aria-live="polite">
                {input.length}/{MAX_INPUT_LENGTH_ASSESSMENT}
              </div>
            )}
          </div>
        </>
      )}
    </>
  );

  if (embedded) {
    return (
      <div className={`${styles.container} ${styles.containerEmbedded}`} style={{ display: 'flex', flexDirection: 'column' }}>
        {content}
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
      onClick={(e) => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className={styles.container} style={{ maxWidth: '480px', width: '100%', maxHeight: '80vh', boxShadow: '0 8px 32px rgba(0,0,0,0.15)' }} onClick={(e) => e.stopPropagation()}>
        {content}
      </div>
    </div>
  );
}
