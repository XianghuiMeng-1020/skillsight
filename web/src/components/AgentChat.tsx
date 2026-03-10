'use client';

import { useState, useCallback } from 'react';
import { studentBff } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';
import { logger } from '@/lib/logger';

export type AgentChatMode = 'assessment' | 'resume_review';

export interface AgentChatProps {
  mode: AgentChatMode;
  skillId?: string;
  skillName?: string;
  title?: string;
  onClose: () => void;
  onComplete?: (assessment?: { level: number; evidence_chunk_ids: string[]; why?: string }) => void;
  /** Optional doc IDs; if not provided, backend uses all consented docs */
  docIds?: string[];
  /** Render as embedded panel (no overlay) */
  embedded?: boolean;
}

const ROBOT_AVATAR = (
  <span
    style={{
      width: 32,
      height: 32,
      borderRadius: '50%',
      background: 'linear-gradient(135deg, var(--sage), var(--sage-dark))',
      color: 'white',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: '1rem',
      flexShrink: 0,
    }}
  >
    🤖
  </span>
);

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
  const { t } = useLanguage();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Array<{ role: string; content: string }>>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [concluded, setConcluded] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const startSession = useCallback(async () => {
    setStartError(null);
    setLoading(true);
    try {
      const res = await studentBff.tutorSessionStart(skillId, docIds, mode);
      setSessionId(res.session_id);
    } catch (e) {
      logger.error('AgentChat session start failed', e);
      setStartError(e instanceof Error ? e.message : 'Failed to start session');
    } finally {
      setLoading(false);
    }
  }, [skillId, docIds, mode]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || !sessionId || loading || concluded) return;
    setInput('');
    setTurns((prev) => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    try {
      const res = await studentBff.tutorSessionMessage(sessionId, text);
      setTurns((prev) => [...prev, { role: 'assistant', content: res.reply }]);
      if (res.concluded && res.assessment) {
        setConcluded(true);
        onComplete?.(res.assessment);
      }
    } catch (e) {
      logger.error('AgentChat message failed', e);
      setTurns((prev) => [
        ...prev,
        { role: 'assistant', content: t('skills.tutorError') || 'Sorry, something went wrong. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, sessionId, loading, concluded, onComplete, t]);

  const displayTitle =
    title ||
    (mode === 'resume_review'
      ? (t('agent.resumeReview') as string) || 'Review My Resume'
      : (t('skills.tutorTitle') as string) + (skillName ? ` — ${skillName}` : ''));

  const content = (
    <>
      <div
        style={{
          padding: '1rem',
          borderBottom: '1px solid var(--gray-200)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: embedded ? 'transparent' : 'var(--gray-50)',
        }}
      >
        <span style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {ROBOT_AVATAR}
          {displayTitle}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onClose}
          disabled={loading}
          aria-label="Close"
        >
          {t('skills.tutorClose') || 'Close'}
        </button>
      </div>

      <div
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '1rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
          minHeight: embedded ? 280 : 320,
        }}
      >
        {!sessionId && !startError && (
          <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--gray-500)' }}>
            {loading ? (
              <>
                <span className="spinner" style={{ display: 'inline-block', marginRight: '0.5rem' }} />
                Starting...
              </>
            ) : (
              <button type="button" className="btn btn-primary" onClick={startSession}>
                {mode === 'resume_review' ? 'Start Resume Review' : 'Start Assessment'}
              </button>
            )}
          </div>
        )}

        {startError && (
          <div className="alert alert-error" style={{ margin: 0 }}>
            {startError}
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setStartError(null)}>
              Retry
            </button>
          </div>
        )}

        {sessionId && turns.length === 0 && !loading && (
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
            {mode === 'resume_review'
              ? 'Share your resume or ask for feedback. I\'ll suggest improvements based on your evidence.'
              : (t('skills.tutorPlaceholder') as string) || 'Type your message...'}
          </p>
        )}

        {turns.map((turn, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: '0.5rem',
              alignSelf: turn.role === 'user' ? 'flex-end' : 'flex-start',
              flexDirection: turn.role === 'user' ? 'row-reverse' : 'row',
              maxWidth: '90%',
            }}
          >
            {turn.role === 'assistant' && ROBOT_AVATAR}
            <div
              style={{
                padding: '0.75rem 1rem',
                borderRadius: '12px',
                background: turn.role === 'user' ? 'var(--peach, #fef3c7)' : 'white',
                border: '1px solid var(--gray-200)',
                fontSize: '0.875rem',
                whiteSpace: 'pre-wrap',
              }}
            >
              {turn.content}
            </div>
          </div>
        ))}

        {concluded && mode === 'assessment' && (
          <p style={{ fontSize: '0.8125rem', color: 'var(--sage)', fontWeight: 500 }}>
            {t('skills.tutorConcluded') || 'Assessment concluded.'}
          </p>
        )}
      </div>

      {sessionId && (
        <div style={{ padding: '1rem', borderTop: '1px solid var(--gray-200)' }}>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
              placeholder={t('skills.tutorPlaceholder') as string || 'Type your message...'}
              disabled={loading || concluded}
              style={{ flex: 1, padding: '0.5rem 0.75rem', borderRadius: '8px', border: '1px solid var(--gray-200)' }}
            />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={sendMessage}
              disabled={!input.trim() || loading || concluded}
            >
              {loading ? '…' : (t('skills.tutorSend') as string) || 'Send'}
            </button>
          </div>
        </div>
      )}
    </>
  );

  if (embedded) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          background: 'white',
          borderRadius: '12px',
          border: '1px solid var(--gray-200)',
          overflow: 'hidden',
        }}
      >
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
      <div
        style={{
          background: 'var(--gray-50)',
          borderRadius: '12px',
          maxWidth: '480px',
          width: '100%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {content}
      </div>
    </div>
  );
}
