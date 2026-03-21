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

const BUILTIN_PREVIEWS: Record<string, {
  gradient: string;
  accent: string;
  icon: string;
  fontStyle: string;
  layoutPreview: 'classic' | 'modern' | 'creative' | 'academic';
}> = {
  professional_classic: {
    gradient: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
    accent: '#e2b04a',
    icon: '📋',
    fontStyle: 'Calibri',
    layoutPreview: 'classic',
  },
  modern_tech: {
    gradient: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)',
    accent: '#38bdf8',
    icon: '💻',
    fontStyle: 'Segoe UI',
    layoutPreview: 'modern',
  },
  creative_portfolio: {
    gradient: 'linear-gradient(135deg, #4c1d95 0%, #6d28d9 50%, #7c3aed 100%)',
    accent: '#c4b5fd',
    icon: '🎨',
    fontStyle: 'Georgia',
    layoutPreview: 'creative',
  },
  academic_research: {
    gradient: 'linear-gradient(135deg, #0a2a4a 0%, #14455e 50%, #1e6070 100%)',
    accent: '#99d5c9',
    icon: '🎓',
    fontStyle: 'Times New Roman',
    layoutPreview: 'academic',
  },
};

function TemplateMiniPreview({ layout, accent }: { layout: string; accent: string }) {
  const barStyle = (w: string, opacity = 0.5) => ({
    height: 4,
    borderRadius: 2,
    width: w,
    background: accent,
    opacity,
    marginBottom: 3,
  });
  const lineStyle = (w: string) => ({
    height: 3,
    borderRadius: 1.5,
    width: w,
    background: 'rgba(255,255,255,0.25)',
    marginBottom: 2,
  });

  if (layout === 'classic') {
    return (
      <div style={{ padding: '12px 14px' }}>
        <div style={{ ...barStyle('60%', 0.9), height: 6, marginBottom: 6 }} />
        <div style={{ ...barStyle('40%', 0.6), marginBottom: 8 }} />
        <div style={lineStyle('100%')} />
        <div style={lineStyle('90%')} />
        <div style={lineStyle('85%')} />
        <div style={{ height: 5 }} />
        <div style={{ ...barStyle('35%', 0.7), marginBottom: 4 }} />
        <div style={lineStyle('95%')} />
        <div style={lineStyle('80%')} />
        <div style={lineStyle('70%')} />
      </div>
    );
  }

  if (layout === 'modern') {
    return (
      <div style={{ display: 'flex', height: '100%' }}>
        <div style={{ width: '35%', background: 'rgba(0,0,0,0.3)', padding: '10px 8px' }}>
          <div style={{ width: 20, height: 20, borderRadius: '50%', background: accent, opacity: 0.8, marginBottom: 6 }} />
          <div style={lineStyle('80%')} />
          <div style={lineStyle('60%')} />
          <div style={{ height: 6 }} />
          <div style={lineStyle('70%')} />
          <div style={lineStyle('50%')} />
        </div>
        <div style={{ flex: 1, padding: '10px 8px' }}>
          <div style={{ ...barStyle('70%', 0.8), height: 5, marginBottom: 6 }} />
          <div style={lineStyle('100%')} />
          <div style={lineStyle('90%')} />
          <div style={lineStyle('80%')} />
          <div style={{ height: 4 }} />
          <div style={{ ...barStyle('45%', 0.6), marginBottom: 4 }} />
          <div style={lineStyle('95%')} />
          <div style={lineStyle('75%')} />
        </div>
      </div>
    );
  }

  if (layout === 'creative') {
    return (
      <div style={{ padding: '12px 14px' }}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 8, alignItems: 'center' }}>
          <div style={{ width: 16, height: 16, borderRadius: 4, background: accent, opacity: 0.9 }} />
          <div style={{ ...barStyle('50%', 0.9), height: 7, marginBottom: 0 }} />
        </div>
        <div style={{ ...barStyle('30%', 0.5), marginBottom: 8 }} />
        <div style={lineStyle('100%')} />
        <div style={lineStyle('95%')} />
        <div style={lineStyle('60%')} />
        <div style={{ height: 5 }} />
        <div style={{ display: 'flex', gap: 4 }}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{ flex: 1, height: 3, borderRadius: 1.5, background: accent, opacity: 0.3 }} />
          ))}
        </div>
      </div>
    );
  }

  // academic
  return (
    <div style={{ padding: '12px 14px', textAlign: 'center' }}>
      <div style={{ ...barStyle('50%', 0.9), height: 6, margin: '0 auto 4px' }} />
      <div style={{ ...barStyle('35%', 0.5), margin: '0 auto 8px' }} />
      <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.4, marginBottom: 8 }} />
      <div style={{ textAlign: 'left' }}>
        <div style={lineStyle('100%')} />
        <div style={lineStyle('90%')} />
        <div style={lineStyle('95%')} />
        <div style={lineStyle('80%')} />
        <div style={{ height: 5 }} />
        <div style={{ ...barStyle('40%', 0.6), marginBottom: 4 }} />
        <div style={lineStyle('85%')} />
        <div style={lineStyle('70%')} />
      </div>
    </div>
  );
}

export function TemplateGallery({ reviewId }: TemplateGalleryProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
      let blob: Blob;
      try {
        blob = base64ToBlob(res.content_base64, res.mime_type || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
      } catch {
        addToast('error', t('common.error') || 'Invalid download data.');
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = res.filename || 'resume.docx';
      a.click();
      URL.revokeObjectURL(url);
      addToast('success', t('resume.exportSuccess'));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      addToast('error', msg);
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

  const builtinTemplates: TemplateItem[] = templates.length > 0 ? templates : [
    {
      template_id: '__professional_classic',
      name: 'Professional Classic',
      description: t('resume.tmplDescClassic') || 'Clean, traditional layout suitable for finance and consulting roles.',
      industry_tags: ['finance', 'consulting', 'corporate'],
      template_file: 'professional_classic.docx',
    },
    {
      template_id: '__modern_tech',
      name: 'Modern Tech',
      description: t('resume.tmplDescTech') || 'Contemporary design for technology and engineering positions.',
      industry_tags: ['technology', 'engineering', 'software'],
      template_file: 'modern_tech.docx',
    },
    {
      template_id: '__creative_portfolio',
      name: 'Creative Portfolio',
      description: t('resume.tmplDescCreative') || 'Stylish layout for marketing, design, and creative roles.',
      industry_tags: ['marketing', 'design', 'creative'],
      template_file: 'creative_portfolio.docx',
    },
    {
      template_id: '__academic_research',
      name: 'Academic Research',
      description: t('resume.tmplDescAcademic') || 'Structured format for research and academia applications.',
      industry_tags: ['research', 'academia', 'education'],
      template_file: 'academic_research.docx',
    },
  ];

  const getPreviewKey = (tmpl: TemplateItem): string => {
    const file = tmpl.template_file || '';
    const key = file.replace(/\.docx$/i, '');
    return key in BUILTIN_PREVIEWS ? key : '';
  };

  return (
    <>
      <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step5Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '1.25rem' }}>{t('resume.step5Desc')}</p>

      <div className={styles.templateGrid}>
        {builtinTemplates.map((tmpl) => {
          const previewKey = getPreviewKey(tmpl);
          const preview = previewKey ? BUILTIN_PREVIEWS[previewKey] : null;
          const isSelected = selectedId === tmpl.template_id;

          return (
            <div
              key={tmpl.template_id}
              className={styles.templateCard}
              style={{
                cursor: 'pointer',
                border: isSelected ? '2px solid var(--primary)' : '1px solid var(--gray-200)',
                transform: isSelected ? 'translateY(-2px)' : undefined,
                boxShadow: isSelected ? '0 4px 12px rgba(99,102,241,0.15)' : undefined,
              }}
              onClick={() => setSelectedId(tmpl.template_id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setSelectedId(tmpl.template_id)}
              aria-pressed={isSelected}
            >
              {/* Visual Preview */}
              <div
                style={{
                  background: preview?.gradient || 'linear-gradient(135deg, #374151, #4b5563)',
                  borderRadius: 'var(--radius)',
                  height: 140,
                  marginBottom: '0.75rem',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                {preview && (
                  <div style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <div style={{
                      width: '75%',
                      height: '85%',
                      background: 'rgba(255,255,255,0.08)',
                      borderRadius: 4,
                      overflow: 'hidden',
                      backdropFilter: 'blur(2px)',
                    }}>
                      <TemplateMiniPreview layout={preview.layoutPreview} accent={preview.accent} />
                    </div>
                  </div>
                )}
                {isSelected && (
                  <div style={{
                    position: 'absolute',
                    top: 8,
                    right: 8,
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    background: 'var(--primary)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#fff',
                    fontSize: '14px',
                    fontWeight: 700,
                  }}>
                    ✓
                  </div>
                )}
              </div>

              {/* Info */}
              <h3 style={{ margin: '0 0 0.35rem 0', fontSize: '1rem', fontWeight: 600 }}>
                {preview?.icon ? `${preview.icon} ` : ''}{tmpl.name}
              </h3>
              {tmpl.description && (
                <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.825rem', color: 'var(--gray-500)', lineHeight: 1.4 }}>
                  {tmpl.description}
                </p>
              )}
              {tmpl.industry_tags && tmpl.industry_tags.length > 0 && (
                <div className={styles.templateTags}>
                  {tmpl.industry_tags.map((tag) => (
                    <span key={tag} className={styles.templateTag}>{tag}</span>
                  ))}
                </div>
              )}

              {/* Actions */}
              <div style={{ marginTop: '0.75rem' }}>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  style={{ width: '100%' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleApply(tmpl.template_id);
                  }}
                  disabled={applying === tmpl.template_id}
                >
                  {applying === tmpl.template_id
                    ? (t('common.loading') || 'Generating...')
                    : (t('resume.applyAndExport') || 'Apply & Download')}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {builtinTemplates.length === 0 && (
        <p style={{ color: 'var(--gray-500)' }}>{t('resume.noTemplates') || 'No templates available.'}</p>
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
