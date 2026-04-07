'use client';

import { useEffect, useMemo, useState } from 'react';
import { studentBff } from '@/lib/bffClient';

interface LivePreviewProps {
  reviewId: string;
  templateId: string;
  resumeOverrideText?: string;
  templateOptions?: Record<string, unknown>;
}

export default function LivePreview({ reviewId, templateId, resumeOverrideText, templateOptions }: LivePreviewProps) {
  const [html, setHtml] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const srcDoc = useMemo(() => html || '<p style="padding:16px;color:#666">Preview unavailable.</p>', [html]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const content = await studentBff.resumeReviewPreviewHtml(reviewId, templateId, {
          resumeOverrideText,
          templateOptions,
        });
        if (!cancelled) setHtml(content);
      } catch {
        if (!cancelled) setHtml('<p style="padding:16px;color:#666">Preview failed.</p>');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reviewId, templateId, resumeOverrideText, templateOptions]);

  return (
    <div style={{ border: '1px solid var(--gray-200)', borderRadius: 12, overflow: 'hidden', minHeight: 380, background: '#fff' }}>
      <div style={{ padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--gray-200)', fontSize: 12, color: 'var(--gray-600)' }}>
        {loading ? 'Loading preview...' : 'Live preview'}
      </div>
      <iframe title="resume-live-preview" srcDoc={srcDoc} style={{ width: '100%', height: 420, border: 'none' }} />
    </div>
  );
}
