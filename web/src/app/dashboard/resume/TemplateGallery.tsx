'use client';

import { useEffect, useState, useCallback } from 'react';
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

/* ──────────────────────────────────────────────────────────────
 * 8 template visual configs – each has a unique layout preview
 * ────────────────────────────────────────────────────────────── */

interface TemplateVisual {
  gradient: string;
  accent: string;
  icon: string;
  fontLabel: string;
  layoutType: string;
  atsLevel: 'high' | 'medium' | 'low';
}

const TEMPLATE_VISUALS: Record<string, TemplateVisual> = {
  professional_classic: {
    gradient: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
    accent: '#e2b04a',
    icon: '📋',
    fontLabel: 'Calibri',
    layoutType: 'classic',
    atsLevel: 'high',
  },
  modern_tech: {
    gradient: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)',
    accent: '#38bdf8',
    icon: '💻',
    fontLabel: 'Arial',
    layoutType: 'sidebar-dark',
    atsLevel: 'medium',
  },
  creative_portfolio: {
    gradient: 'linear-gradient(135deg, #4c1d95 0%, #6d28d9 50%, #7c3aed 100%)',
    accent: '#c4b5fd',
    icon: '🎨',
    fontLabel: 'Georgia',
    layoutType: 'creative',
    atsLevel: 'low',
  },
  academic_research: {
    gradient: 'linear-gradient(135deg, #0a2a4a 0%, #14455e 50%, #1e6070 100%)',
    accent: '#99d5c9',
    icon: '🎓',
    fontLabel: 'Times New Roman',
    layoutType: 'academic',
    atsLevel: 'high',
  },
  executive: {
    gradient: 'linear-gradient(135deg, #1b2a4a 0%, #2c3e6b 50%, #3d5291 100%)',
    accent: '#bf943e',
    icon: '👔',
    fontLabel: 'Cambria',
    layoutType: 'executive',
    atsLevel: 'high',
  },
  minimalist_clean: {
    gradient: 'linear-gradient(135deg, #f5f5f5 0%, #e5e5e5 50%, #d4d4d4 100%)',
    accent: '#111111',
    icon: '✨',
    fontLabel: 'Calibri Light',
    layoutType: 'minimalist',
    atsLevel: 'high',
  },
  corporate_elegance: {
    gradient: 'linear-gradient(135deg, #134e4a 0%, #115e59 50%, #0f766e 100%)',
    accent: '#14b8a6',
    icon: '🏢',
    fontLabel: 'Calibri',
    layoutType: 'corporate-header',
    atsLevel: 'high',
  },
  fresh_graduate: {
    gradient: 'linear-gradient(135deg, #1e40af 0%, #2563eb 50%, #3b82f6 100%)',
    accent: '#93c5fd',
    icon: '🚀',
    fontLabel: 'Arial',
    layoutType: 'graduate',
    atsLevel: 'high',
  },
};

/* ──────────────────────────────────────────────────────────────
 * Mini layout preview – distinct visual for each template
 * ────────────────────────────────────────────────────────────── */

function TemplateMiniPreview({ layoutType, accent }: { layoutType: string; accent: string }) {
  const bar = (w: string, opacity = 0.5, h = 4, mb = 3, color = accent) => ({
    height: h,
    borderRadius: h / 2,
    width: w,
    background: color,
    opacity,
    marginBottom: mb,
  });
  const line = (w: string, opacity = 0.25) => ({
    height: 3,
    borderRadius: 1.5,
    width: w,
    background: `rgba(255,255,255,${opacity})`,
    marginBottom: 2,
  });
  const darkLine = (w: string, opacity = 0.15) => ({
    height: 3,
    borderRadius: 1.5,
    width: w,
    background: `rgba(0,0,0,${opacity})`,
    marginBottom: 2,
  });

  if (layoutType === 'classic') {
    return (
      <div style={{ padding: '12px 14px' }}>
        <div style={{ textAlign: 'center', marginBottom: 6 }}>
          <div style={{ ...bar('60%', 0.9, 6, 4), margin: '0 auto' }} />
          <div style={{ ...bar('45%', 0.4, 2, 6), margin: '0 auto' }} />
        </div>
        <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.6, marginBottom: 6 }} />
        <div style={{ ...bar('30%', 0.7, 4, 3) }} />
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.15)', marginBottom: 4 }} />
        <div style={line('100%')} />
        <div style={line('90%')} />
        <div style={line('85%')} />
        <div style={{ height: 4 }} />
        <div style={{ ...bar('35%', 0.7, 4, 3) }} />
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.15)', marginBottom: 4 }} />
        <div style={line('95%')} />
        <div style={line('80%')} />
      </div>
    );
  }

  if (layoutType === 'sidebar-dark') {
    return (
      <div style={{ display: 'flex', height: '100%' }}>
        <div style={{ width: '32%', background: 'rgba(0,0,0,0.4)', padding: '10px 6px' }}>
          <div style={{ ...bar('70%', 0.9, 5, 4), background: '#fff' }} />
          <div style={line('60%', 0.3)} />
          <div style={line('55%', 0.3)} />
          <div style={{ height: 6 }} />
          <div style={{ ...bar('40%', 0.8, 3, 3), background: accent }} />
          <div style={line('65%', 0.25)} />
          <div style={line('50%', 0.25)} />
          <div style={{ height: 4 }} />
          <div style={{ ...bar('40%', 0.8, 3, 3), background: accent }} />
          <div style={line('55%', 0.25)} />
          <div style={line('45%', 0.25)} />
        </div>
        <div style={{ flex: 1, padding: '10px 8px' }}>
          <div style={{ ...bar('55%', 0.8, 5, 5) }} />
          <div style={{ ...bar('100%', 0.3, 1, 6), background: accent }} />
          <div style={line('100%')} />
          <div style={line('90%')} />
          <div style={line('80%')} />
          <div style={{ height: 5 }} />
          <div style={{ ...bar('45%', 0.8, 5, 5) }} />
          <div style={{ ...bar('100%', 0.3, 1, 6), background: accent }} />
          <div style={line('95%')} />
          <div style={line('75%')} />
        </div>
      </div>
    );
  }

  if (layoutType === 'creative') {
    return (
      <div style={{ padding: '12px 14px' }}>
        {/* Large first-letter + name (matches DOCX output) */}
        <div style={{ display: 'flex', gap: 2, marginBottom: 4, alignItems: 'baseline' }}>
          <div style={{ width: 12, height: 20, borderRadius: 2, background: accent, opacity: 0.95 }} />
          <div style={{ ...bar('40%', 0.5, 8, 0), background: 'rgba(255,255,255,0.35)' }} />
        </div>
        {/* Purple accent bar */}
        <div style={{ borderTop: `2px solid ${accent}`, opacity: 0.7, marginBottom: 6 }} />
        <div style={{ ...bar('55%', 0.25, 2, 8) }} />
        {/* Section header with purple title + underline */}
        <div style={{ ...bar('30%', 0.8, 4, 2), background: accent }} />
        <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
        <div style={line('100%')} />
        <div style={line('90%')} />
        <div style={{ height: 4 }} />
        <div style={{ ...bar('25%', 0.8, 4, 2), background: accent }} />
        <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
        <div style={line('95%')} />
        <div style={line('70%')} />
      </div>
    );
  }

  if (layoutType === 'academic') {
    return (
      <div style={{ padding: '12px 14px', textAlign: 'center' }}>
        <div style={{ ...bar('55%', 0.5, 3, 3), margin: '0 auto', letterSpacing: 2 }} />
        <div style={{ ...bar('50%', 0.6, 6, 4), margin: '0 auto' }} />
        <div style={{ borderTop: `2px double ${accent}`, opacity: 0.5, marginBottom: 6 }} />
        <div style={{ ...bar('40%', 0.4, 2, 8), margin: '0 auto' }} />
        <div style={{ textAlign: 'left' }}>
          <div style={{ ...bar('35%', 0.7, 4, 2) }} />
          <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
          <div style={{ paddingLeft: 8 }}>
            <div style={line('90%')} />
            <div style={line('85%')} />
          </div>
          <div style={{ height: 4 }} />
          <div style={{ ...bar('30%', 0.7, 4, 2) }} />
          <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
          <div style={{ paddingLeft: 8 }}>
            <div style={line('80%')} />
            <div style={line('70%')} />
          </div>
        </div>
      </div>
    );
  }

  if (layoutType === 'executive') {
    return (
      <div style={{ padding: '12px 14px' }}>
        <div style={{ borderTop: `2px solid ${accent}`, marginBottom: 8 }} />
        <div style={{ textAlign: 'center', marginBottom: 6 }}>
          <div style={{ ...bar('55%', 0.8, 7, 3), margin: '0 auto', letterSpacing: 3 }} />
          <div style={{ ...bar('45%', 0.3, 2, 4), margin: '0 auto' }} />
        </div>
        <div style={{ borderTop: `2px solid ${accent}`, marginBottom: 8 }} />
        <div style={{ ...bar('35%', 0.7, 4, 2) }} />
        <div style={{ borderBottom: `1px solid ${accent}`, opacity: 0.5, marginBottom: 4, paddingBottom: 2 }} />
        <div style={line('100%')} />
        <div style={line('90%')} />
        <div style={{ height: 4 }} />
        <div style={{ ...bar('30%', 0.7, 4, 2) }} />
        <div style={{ borderBottom: `1px solid ${accent}`, opacity: 0.5, marginBottom: 4, paddingBottom: 2 }} />
        <div style={line('85%')} />
        <div style={line('75%')} />
      </div>
    );
  }

  if (layoutType === 'minimalist') {
    const isDark = false;
    return (
      <div style={{ padding: '16px 14px', background: isDark ? undefined : 'rgba(255,255,255,0.6)' }}>
        <div style={{ ...bar('50%', 0.8, 7, 3, '#111') }} />
        <div style={{ ...bar('55%', 0.15, 2, 14, '#999') }} />
        <div style={{ ...bar('25%', 0.6, 3, 2, '#111'), letterSpacing: 2 }} />
        <div style={{ borderTop: '1px solid rgba(0,0,0,0.12)', marginBottom: 6 }} />
        <div style={darkLine('100%')} />
        <div style={darkLine('90%')} />
        <div style={darkLine('80%')} />
        <div style={{ height: 8 }} />
        <div style={{ ...bar('30%', 0.6, 3, 2, '#111'), letterSpacing: 2 }} />
        <div style={{ borderTop: '1px solid rgba(0,0,0,0.12)', marginBottom: 6 }} />
        <div style={darkLine('95%')} />
        <div style={darkLine('75%')} />
      </div>
    );
  }

  if (layoutType === 'corporate-header') {
    return (
      <div style={{ padding: '0' }}>
        {/* Teal header block with name + contact */}
        <div style={{ background: 'rgba(0,0,0,0.35)', padding: '10px 12px', textAlign: 'center', marginBottom: 3 }}>
          <div style={{ ...bar('55%', 0.9, 6, 3, '#fff'), margin: '0 auto', letterSpacing: 2 }} />
          <div style={{ ...bar('50%', 0.5, 2, 0), margin: '0 auto', background: accent }} />
        </div>
        {/* Teal accent line */}
        <div style={{ borderTop: `2px solid ${accent}`, opacity: 0.6, margin: '0 12px 6px' }} />
        {/* Single-column body sections */}
        <div style={{ padding: '2px 12px' }}>
          <div style={{ ...bar('30%', 0.7, 3, 2) }} />
          <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
          <div style={line('100%')} />
          <div style={line('90%')} />
          <div style={line('85%')} />
          <div style={{ height: 4 }} />
          <div style={{ ...bar('35%', 0.7, 3, 2) }} />
          <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
          <div style={line('95%')} />
          <div style={line('80%')} />
        </div>
      </div>
    );
  }

  // graduate
  return (
    <div style={{ padding: '0' }}>
      <div style={{ background: 'rgba(0,0,0,0.25)', padding: '10px 12px', textAlign: 'center', marginBottom: 6 }}>
        <div style={{ ...bar('55%', 0.9, 6, 3, '#fff'), margin: '0 auto', letterSpacing: 2 }} />
        <div style={{ ...bar('50%', 0.4, 2, 0, '#fff'), margin: '0 auto' }} />
      </div>
      <div style={{ padding: '4px 12px' }}>
        <div style={{ display: 'flex', gap: 3, alignItems: 'center', marginBottom: 3 }}>
          <div style={{ width: 5, height: 5, borderRadius: '50%', background: accent }} />
          <div style={{ ...bar('30%', 0.7, 3, 0) }} />
        </div>
        <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
        <div style={line('90%')} />
        <div style={line('80%')} />
        <div style={{ height: 3 }} />
        <div style={{ display: 'flex', gap: 3, alignItems: 'center', marginBottom: 3 }}>
          <div style={{ width: 5, height: 5, borderRadius: '50%', background: accent }} />
          <div style={{ ...bar('35%', 0.7, 3, 0) }} />
        </div>
        <div style={{ borderTop: `1px solid ${accent}`, opacity: 0.3, marginBottom: 4 }} />
        <div style={line('100%')} />
        <div style={line('85%')} />
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────
 * Full-page preview modal – shows a large rendered preview
 * ────────────────────────────────────────────────────────────── */

function TemplatePreviewModal({
  template,
  visual,
  onClose,
  onApply,
  applying,
  t,
}: {
  template: TemplateItem;
  visual: TemplateVisual | null;
  onClose: () => void;
  onApply: () => void;
  applying: boolean;
  t: (k: string) => string;
}) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(4px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--white, #fff)',
          borderRadius: 16,
          maxWidth: 640,
          width: '95%',
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: '0 24px 48px rgba(0,0,0,0.25)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Large preview */}
        <div
          style={{
            background: visual?.gradient || 'linear-gradient(135deg,#374151,#4b5563)',
            borderRadius: '16px 16px 0 0',
            height: 340,
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <div style={{
              width: '60%',
              height: '85%',
              background: 'rgba(255,255,255,0.08)',
              borderRadius: 6,
              overflow: 'hidden',
              backdropFilter: 'blur(2px)',
              boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            }}>
              {visual && <TemplateMiniPreview layoutType={visual.layoutType} accent={visual.accent} />}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              position: 'absolute',
              top: 12,
              right: 12,
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: 'none',
              background: 'rgba(0,0,0,0.4)',
              color: '#fff',
              fontSize: 18,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            ✕
          </button>
        </div>

        {/* Details */}
        <div style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 24 }}>{visual?.icon}</span>
            <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700 }}>{template.name}</h2>
          </div>

          {template.description && (
            <p style={{ color: 'var(--gray-600)', fontSize: '0.9rem', lineHeight: 1.5, marginBottom: 12 }}>
              {template.description}
            </p>
          )}

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
            {visual?.fontLabel && (
              <span style={{ color: 'var(--gray-400)', fontSize: '0.8rem' }}>
                Font: {visual.fontLabel}
              </span>
            )}
            {visual?.atsLevel && (
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: 4,
                  background: visual.atsLevel === 'high' ? '#dcfce7' : visual.atsLevel === 'medium' ? '#fef9c3' : '#fee2e2',
                  color: visual.atsLevel === 'high' ? '#166534' : visual.atsLevel === 'medium' ? '#854d0e' : '#991b1b',
                }}
              >
                {visual.atsLevel === 'high'
                  ? (t('resume.atsHigh') || 'ATS Friendly')
                  : visual.atsLevel === 'medium'
                    ? (t('resume.atsMedium') || 'ATS Moderate')
                    : (t('resume.atsLow') || 'ATS Limited')}
              </span>
            )}
          </div>

          {template.industry_tags && template.industry_tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
              {template.industry_tags.map((tag) => (
                <span
                  key={tag}
                  style={{
                    fontSize: '0.75rem',
                    padding: '4px 10px',
                    borderRadius: 999,
                    background: 'var(--teal-50, #f0fdfa)',
                    color: 'var(--teal-dark, #134e4a)',
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', gap: 10 }}>
            <button
              type="button"
              className="btn btn-primary"
              style={{ flex: 1 }}
              onClick={onApply}
              disabled={applying}
            >
              {applying
                ? (t('common.loading') || 'Generating...')
                : (t('resume.applyAndExport') || 'Apply & Download')}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              style={{ minWidth: 80 }}
            >
              {t('common.cancel') || 'Cancel'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────
 * Main gallery component
 * ────────────────────────────────────────────────────────────── */

const FALLBACK_TEMPLATES: TemplateItem[] = [
  {
    template_id: '__professional_classic',
    name: 'Professional Classic',
    description: 'Clean single-column layout with centered header and horizontal rules. ATS-friendly.',
    industry_tags: ['finance', 'consulting', 'corporate'],
    template_file: 'professional_classic.docx',
  },
  {
    template_id: '__modern_tech',
    name: 'Modern Tech',
    description: 'Two-column layout with dark sidebar. Popular LinkedIn-style design for tech roles.',
    industry_tags: ['technology', 'engineering', 'software'],
    template_file: 'modern_tech.docx',
  },
  {
    template_id: '__creative_portfolio',
    name: 'Creative Portfolio',
    description: 'Bold purple accents with decorative markers. Expressive layout for creative pros.',
    industry_tags: ['marketing', 'design', 'creative'],
    template_file: 'creative_portfolio.docx',
  },
  {
    template_id: '__academic_research',
    name: 'Academic CV',
    description: 'Formal Curriculum Vitae format. Standard for academic and research positions.',
    industry_tags: ['research', 'academia', 'education'],
    template_file: 'academic_research.docx',
  },
  {
    template_id: '__executive',
    name: 'Executive',
    description: 'Premium navy and gold design with Cambria font. Refined elegance for leadership.',
    industry_tags: ['leadership', 'executive', 'management'],
    template_file: 'executive.docx',
  },
  {
    template_id: '__minimalist_clean',
    name: 'Minimalist Clean',
    description: 'Ultra-clean monochrome layout with maximum whitespace. Content speaks for itself.',
    industry_tags: ['any industry', 'startup', 'modern'],
    template_file: 'minimalist_clean.docx',
  },
  {
    template_id: '__corporate_elegance',
    name: 'Corporate Elegance',
    description: 'Teal header block with single-column body. ATS-friendly corporate style.',
    industry_tags: ['business', 'operations', 'corporate'],
    template_file: 'corporate_elegance.docx',
  },
  {
    template_id: '__fresh_graduate',
    name: 'Fresh Graduate',
    description: 'Compact layout with blue header bar and skills-first ordering for students.',
    industry_tags: ['entry-level', 'student', 'internship'],
    template_file: 'fresh_graduate.docx',
  },
];

export function TemplateGallery({ reviewId }: TemplateGalleryProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [previewTemplate, setPreviewTemplate] = useState<TemplateItem | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await studentBff.getResumeTemplates();
        setTemplates(res.templates?.length ? res.templates : []);
      } catch {
        setTemplates([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleApply = useCallback(async (templateId: string) => {
    setApplying(templateId);
    try {
      const res = await studentBff.resumeReviewApplyTemplate(reviewId, templateId);
      const blob = base64ToBlob(
        res.content_base64,
        res.mime_type || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = res.filename || 'resume.docx';
      a.click();
      URL.revokeObjectURL(url);
      addToast('success', t('resume.exportSuccess'));
      setPreviewTemplate(null);
    } catch (e: unknown) {
      let msg = e instanceof Error ? e.message : String(e);
      if (e && typeof e === 'object' && 'detail' in e) {
        const detail = (e as { detail: unknown }).detail;
        if (detail && typeof detail === 'object' && 'message' in detail) {
          msg = (detail as { message: string }).message;
        } else if (typeof detail === 'string') {
          msg = detail;
        }
      }
      console.error('[TemplateGallery] apply-template error:', e);
      addToast('error', msg);
    } finally {
      setApplying(null);
    }
  }, [reviewId, addToast, t]);

  if (loading) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step5Title')}</h2>
        <p style={{ color: 'var(--gray-600)' }}>{t('common.loading')}</p>
      </>
    );
  }

  const displayTemplates = templates.length > 0 ? templates : FALLBACK_TEMPLATES;

  const getVisualKey = (tmpl: TemplateItem): string => {
    const file = tmpl.template_file || '';
    const key = file.replace(/\.docx$/i, '');
    return key in TEMPLATE_VISUALS ? key : '';
  };

  return (
    <>
      <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step5Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '0.35rem' }}>{t('resume.step5Desc')}</p>
      <p style={{ fontSize: '0.8125rem', color: 'var(--gray-600)', marginBottom: '1.25rem' }}>{t('resume.atsFullName')}</p>

      <div className={styles.templateGrid}>
        {displayTemplates.map((tmpl) => {
          const vKey = getVisualKey(tmpl);
          const visual = vKey ? TEMPLATE_VISUALS[vKey] : null;

          return (
            <div
              key={tmpl.template_id}
              className={styles.templateCard}
              style={{ cursor: 'pointer' }}
              onClick={() => setPreviewTemplate(tmpl)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setPreviewTemplate(tmpl)}
            >
              {/* Preview thumbnail */}
              <div
                style={{
                  background: visual?.gradient || 'linear-gradient(135deg,#374151,#4b5563)',
                  borderRadius: 'var(--radius)',
                  height: 150,
                  marginBottom: '0.75rem',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                {visual && (
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
                      <TemplateMiniPreview layoutType={visual.layoutType} accent={visual.accent} />
                    </div>
                  </div>
                )}
                {/* Preview badge */}
                <div style={{
                  position: 'absolute',
                  bottom: 8,
                  right: 8,
                  padding: '3px 8px',
                  borderRadius: 4,
                  background: 'rgba(0,0,0,0.5)',
                  color: '#fff',
                  fontSize: '0.65rem',
                  letterSpacing: '0.5px',
                }}>
                  {t('resume.clickToPreview') || 'Click to preview'}
                </div>
              </div>

              {/* Info */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: '0.3rem' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600, flex: 1 }}>
                  {visual?.icon ? `${visual.icon} ` : ''}{tmpl.name}
                </h3>
                {visual?.atsLevel && (
                  <span
                    style={{
                      fontSize: '0.65rem',
                      fontWeight: 600,
                      padding: '2px 6px',
                      borderRadius: 4,
                      whiteSpace: 'nowrap',
                      background: visual.atsLevel === 'high' ? '#dcfce7' : visual.atsLevel === 'medium' ? '#fef9c3' : '#fee2e2',
                      color: visual.atsLevel === 'high' ? '#166534' : visual.atsLevel === 'medium' ? '#854d0e' : '#991b1b',
                    }}
                  >
                    {visual.atsLevel === 'high'
                      ? (t('resume.atsHigh') || 'ATS Friendly')
                      : visual.atsLevel === 'medium'
                        ? (t('resume.atsMedium') || 'ATS Moderate')
                        : (t('resume.atsLow') || 'ATS Limited')}
                  </span>
                )}
              </div>
              {tmpl.description && (
                <p style={{
                  margin: '0 0 0.5rem 0',
                  fontSize: '0.8rem',
                  color: 'var(--gray-500)',
                  lineHeight: 1.4,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}>
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

              {/* Action buttons */}
              <div style={{ marginTop: '0.75rem', display: 'flex', gap: 6 }}>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  style={{ flex: 1 }}
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
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  style={{ minWidth: 36, padding: '0.25rem 0.5rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setPreviewTemplate(tmpl);
                  }}
                  title={t('resume.preview') || 'Preview'}
                >
                  👁
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {displayTemplates.length === 0 && (
        <p style={{ color: 'var(--gray-500)' }}>{t('resume.noTemplates') || 'No templates available.'}</p>
      )}

      {/* Preview modal */}
      {previewTemplate && (
        <TemplatePreviewModal
          template={previewTemplate}
          visual={TEMPLATE_VISUALS[getVisualKey(previewTemplate)] || null}
          onClose={() => setPreviewTemplate(null)}
          onApply={() => handleApply(previewTemplate.template_id)}
          applying={applying === previewTemplate.template_id}
          t={t}
        />
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
