'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { staffBff } from '@/lib/bffClient';

export default function ReviewTicketPage() {
  const { ticketId } = useParams<{ ticketId: string }>();
  const router = useRouter();
  const [ticket, setTicket] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [decision, setDecision] = useState<'approve' | 'reject' | 'needs_more_evidence'>('approve');
  const [comment, setComment] = useState('');
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
    let token: string | null = null;
    if (typeof window !== 'undefined') {
      try {
        token = localStorage.getItem('skillsight_token');
      } catch (e) {
        console.warn('Failed to read token from localStorage:', e);
      }
    }
    fetch(`${API_BASE}/bff/staff/review/${ticketId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => { if (!cancelled) setTicket(data); })
      .catch((e) => { if (!cancelled) setError(e.message || 'Failed to load ticket'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ticketId]);

  const handleResolve = async () => {
    if (!comment.trim() && decision !== 'approve') {
      setError('Please provide a comment for non-approval decisions.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await staffBff.resolveTicket(ticketId, decision, comment);
      setResolved(true);
      setTimeout(() => router.back(), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to resolve ticket');
    } finally {
      setSubmitting(false);
    }
  };

  if (resolved) {
    return (
      <div style={{ minHeight: '100vh', background: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: '#34d399' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>✓</div>
          <h2>Ticket Resolved</h2>
          <p style={{ color: '#64748b' }}>Redirecting back…</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', fontSize: 14 }}>
          ← Back
        </button>
        <span style={{ color: '#475569' }}>|</span>
        <span style={{ color: '#94a3b8' }}>Review Ticket: {ticketId.slice(0, 8)}…</span>
      </nav>

      <div style={{ maxWidth: 700, margin: '48px auto', padding: '0 24px' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Review Ticket</h1>
        <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: '16px 20px', marginBottom: 24 }}>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>Ticket ID</div>
          <div style={{ fontFamily: 'monospace', color: '#94a3b8', fontSize: 14 }}>{ticketId}</div>
        </div>

        {/* Privacy notice */}
        <div style={{ background: '#0f172a', border: '1px solid #1d4ed8', borderRadius: 10, padding: '14px 18px', marginBottom: 28 }}>
          <p style={{ margin: 0, fontSize: 13, color: '#93c5fd' }}>
            <strong>Privacy notice:</strong> This view shows only pointers and metadata. Original student content is not displayed.
          </p>
        </div>

        {error && <p style={{ color: '#f87171', marginBottom: 16 }}>{error}</p>}
        {loading && <p style={{ color: '#64748b' }}>Loading ticket…</p>}

        {!loading && (
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 28 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 24 }}>Resolution</h2>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 14, color: '#94a3b8', marginBottom: 8 }}>Decision</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {(['approve', 'reject', 'needs_more_evidence'] as const).map(d => (
                  <button
                    key={d}
                    onClick={() => setDecision(d)}
                    style={{
                      padding: '8px 16px', borderRadius: 8, border: '2px solid',
                      borderColor: decision === d
                        ? (d === 'approve' ? '#34d399' : d === 'reject' ? '#f87171' : '#fbbf24')
                        : '#334155',
                      background: decision === d
                        ? (d === 'approve' ? '#065f4620' : d === 'reject' ? '#7f1d1d20' : '#78350f20')
                        : 'transparent',
                      color: decision === d
                        ? (d === 'approve' ? '#34d399' : d === 'reject' ? '#f87171' : '#fbbf24')
                        : '#64748b',
                      cursor: 'pointer', fontSize: 13, fontWeight: 600,
                    }}
                  >
                    {d === 'approve' ? '✓ Approve' : d === 'reject' ? '✗ Reject' : '? Needs More Evidence'}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontSize: 14, color: '#94a3b8', marginBottom: 8 }}>
                Comment {decision !== 'approve' && <span style={{ color: '#f87171' }}>*</span>}
              </label>
              <textarea
                value={comment}
                onChange={e => setComment(e.target.value)}
                rows={4}
                placeholder="Explain your decision…"
                style={{
                  width: '100%', padding: '12px 14px', borderRadius: 8, border: '1px solid #475569',
                  background: '#0f172a', color: '#e2e8f0', fontSize: 14, resize: 'vertical', boxSizing: 'border-box',
                }}
              />
            </div>

            <button
              onClick={handleResolve}
              disabled={submitting}
              data-testid="submit-resolve"
              style={{
                padding: '12px 32px', borderRadius: 8, background: '#2563eb', color: '#fff',
                border: 'none', cursor: submitting ? 'not-allowed' : 'pointer', fontSize: 16, fontWeight: 600,
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? 'Submitting…' : 'Submit Resolution'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
