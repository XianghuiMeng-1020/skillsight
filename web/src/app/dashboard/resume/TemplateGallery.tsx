'use client';

import { useEffect, useState } from 'react';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { studentBff } from '@/lib/bffClient';
import styles from './resume.module.css';

interface TemplateGalleryProps {
  reviewId: string;
}

interface TemplateItem {
  template_id: string;
  name: string;
  description?: string;
  industry_tags?: string[];
  preview_url?: string;
  template_file?: string;
}

export function TemplateGallery({ reviewId }: TemplateGalleryProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      try {
        const res = await studentBff.getResumeTemplates();
        setTemplates(res.templates || []);
      } catch {
        setTemplates([]);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  const handleApply = async (templateId: string) => {
    setApplying(templateId);
    try {
      const res = await studentBff.resumeReviewApplyTemplate(reviewId, templateId);
      const blob = base64ToBlob(res.content_base64, res.mime_type || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = res.filename || 'resume.docx';
      a.click();
      URL.revokeObjectURL(url);
      addToast('success', t('resume.exportSuccess') || 'Exported successfully.');
    } catch (e) {
      addToast('error', (e as Error).message);
    } finally {
      setApplying(null);
    }
  };

  if (loading) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step5Title')}</h2>
        <p style={{ color: 'var(--gray-600)' }}>{t('common.loading')}</p>
      </>
    );
  }

  return (
    <>
      <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step5Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>{t('resume.step5Desc')}</p>

      <div className={styles.templateGrid}>
        {templates.map((tmpl) => (
          <div key={tmpl.template_id} className={styles.templateCard}>
            <h3>{tmpl.name}</h3>
            {tmpl.description && <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--gray-600)' }}>{tmpl.description}</p>}
            {tmpl.industry_tags && tmpl.industry_tags.length > 0 && (
              <div className={styles.templateTags}>
                {tmpl.industry_tags.map((tag) => (
                  <span key={tag} className={styles.templateTag}>
                    {tag}
                  </span>
                ))}
              </div>
            )}
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
              {tmpl.preview_url && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setPreviewId(tmpl.template_id)}
                >
                  {t('resume.preview')}
                </button>
              )}
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => handleApply(tmpl.template_id)}
                disabled={applying === tmpl.template_id}
              >
                {applying === tmpl.template_id ? t('common.loading') : t('resume.applyAndExport')}
              </button>
            </div>
          </div>
        ))}
      </div>

      {templates.length === 0 && (
        <p style={{ color: 'var(--gray-500)' }}>{t('resume.noTemplates') || 'No templates available.'}</p>
      )}

      {previewId && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
          }}
          onClick={() => setPreviewId(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            style={{
              background: 'var(--white)',
              padding: '1.5rem',
              borderRadius: 'var(--radius-lg)',
              maxWidth: '90%',
              maxHeight: '80%',
              overflow: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <p style={{ margin: 0, color: 'var(--gray-600)' }}>{t('resume.preview')}</p>
            <p style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>{t('resume.previewNotAvailable') || 'Preview not available for this template.'}</p>
            <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: '1rem' }} onClick={() => setPreviewId(null)}>
              {t('common.close') || 'Close'}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function base64ToBlob(base64: string, mimeType: string): Blob {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mimeType });
}
