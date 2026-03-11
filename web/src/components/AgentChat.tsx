'use client';

import { useState, useCallback, useEffect } from 'react';
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

  const startSession = useCallback(async () => {
    setStartError(null);
    setLoading(true);
    try {
      const res = await studentBff.tutorSessionStart(skillId, docIds, mode);
      setSessionId(res.session_id);
      const greeting = (t('agent.greeting') as string) || '';
      setTurns([{ role: 'assistant', content: greeting, ts: Date.now() }]);
    } catch (e) {
      logger.error('AgentChat session start failed', e);
      setStartError(e instanceof Error ? e.message : 'Failed to start session');
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
          {mode === 'assessment' && sessionId && (
            <span className={styles.turnBadge} aria-label={`Turn ${userTurnCount} of ${MAX_TURNS_ASSESSMENT}`}>
              {userTurnCount}/{MAX_TURNS_ASSESSMENT}
            </span>
          )}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onClose}
          disabled={loading}
          aria-label="Close"
        >
          {t('skills.tutorClose') as string}
        </button>
      </div>

      <div className={`${styles.messages} ${embedded ? styles.messagesEmbedded : ''}`}>
        {!sessionId && !startError && (
          <div className={styles.startBlock}>
            {loading ? (
              <>
                <span className={styles.spinner} />
                {t('skills.loading') as string}
              </>
            ) : null}
          </div>
        )}

        {startError && (
          <div className={`alert alert-error ${styles.errorBlock}`}>
            {startError}
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setStartError(null); setSessionStarted(false); }}>
              Retry
            </button>
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
                aria-label="Send"
              >
                {loading ? '…' : '➤'}
              </button>
            </div>
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
