'use client';

import { useState, useRef, useEffect, DragEvent } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';
import { API_BASE_URL } from '@/lib/api';
import { getToken } from '@/lib/bffClient';
import { useToast } from '@/components/Toast';

interface UploadResult {
  doc_id: string;
  filename: string;
  chunks_created: number;
  consent_id?: string;
}

type ProcessingStage = 'idle' | 'uploading' | 'embedding' | 'assessing' | 'done';

const PURPOSE_KEYS = [
  { value: 'skill_assessment', labelKey: 'upload.purposeSkillAssess', descKey: 'upload.purposeSkillAssessDesc' },
  { value: 'role_alignment', labelKey: 'upload.purposeRoleAlign', descKey: 'upload.purposeRoleAlignDesc' },
  { value: 'portfolio', labelKey: 'upload.purposePortfolio', descKey: 'upload.purposePortfolioDesc' },
] as const;

const SCOPE_KEYS = [
  { value: 'full', labelKey: 'upload.scopeFull', descKey: 'upload.scopeFullDesc' },
  { value: 'excerpt', labelKey: 'upload.scopeExcerpt', descKey: 'upload.scopeExcerptDesc' },
  { value: 'summary', labelKey: 'upload.scopeSummary', descKey: 'upload.scopeSummaryDesc' },
] as const;

export default function UploadPage() {
  const { t, language } = useLanguage();
  const { addToast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [purpose, setPurpose] = useState('');
  const [scope, setScope] = useState('');
  const [uploading, setUploading] = useState(false);
  const [stage, setStage] = useState<ProcessingStage>('idle');
  const [assessProgress, setAssessProgress] = useState({ done: 0, total: 0 });
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ code: string; message: string; next_step: string } | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const existing = localStorage.getItem('skillsight_token');
    if (!existing) {
      fetch(`${API_BASE_URL}/bff/student/auth/dev_login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject_id: 'demo_student', role: 'student' }),
      })
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => {
          if (data?.token) {
            localStorage.setItem('skillsight_token', data.token);
            if (data.role) localStorage.setItem('skillsight_role', data.role);
          }
        })
        .catch(() => {
          const msg = 'Auto-login failed. Please log in manually.';
          setError(msg);
          addToast('error', msg);
        });
    }
  }, []);

  const consentComplete = purpose !== '' && scope !== '';

  const supportedFormats = [
    { icon: '📕', categoryKey: 'upload.typeDoc', formats: 'PDF, DOC, DOCX, TXT, RTF, ODT, MD, PPT, PPTX' },
    { icon: '📊', categoryKey: 'upload.typeTable', formats: 'XLSX, XLS, CSV' },
    { icon: '🖼️', categoryKey: 'upload.typeImage', formats: 'JPG, PNG, WEBP, BMP, TIFF, GIF, SVG, ICO, HEIC' },
    { icon: '🎬', categoryKey: 'upload.typeMedia', formats: 'MP4, WEBM, MOV, AVI, MKV, MP3, WAV, M4A, OGG, FLAC, AAC' },
    { icon: '💻', categoryKey: 'upload.typeCode', formats: 'PY, JS, TS, IPYNB, JAVA, GO, RS, RB, HTML, CSS, JSON...' },
  ];

  const handleDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setError(null);
      setResult(null);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file || !consentComplete) return;

    setUploading(true);
    setStage('uploading');
    setError(null);
    setResult(null);
    setRefusal(null);
    setAssessProgress({ done: 0, total: 0 });

    try {
      const token = typeof window !== 'undefined' ? getToken() : null;
      const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

      // Step 1: Upload
      const formData = new FormData();
      formData.append('file', file);
      formData.append('purpose', purpose);
      formData.append('scope', scope);

      const response = await fetch(`${API_BASE_URL}/bff/student/documents/upload`, {
        method: 'POST',
        headers: authHeaders,
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json();
        const detail = err.detail;
        const refusalPayload =
          detail && typeof detail === 'object' && detail.refusal
            ? detail.refusal
            : detail && typeof detail === 'object' && detail.code
              ? { code: detail.code, message: detail.message ?? '', next_step: detail.next_step ?? '' }
              : null;
        if (refusalPayload && refusalPayload.code) {
          setRefusal(refusalPayload as { code: string; message: string; next_step: string });
        } else {
          throw new Error(typeof detail === 'string' ? detail : t('upload.failed'));
        }
        return;
      }

      const data = await response.json();
      setResult(data);
      const docId = data.doc_id;

      // Step 2: Embed chunks (generate vector embeddings)
      setStage('embedding');
      try {
        await fetch(`${API_BASE_URL}/bff/student/chunks/embed/${docId}`, {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
        });
      } catch {
        // non-fatal: embedding may fail if sentence-transformers not available
      }

      // Step 3: Run AI skill assessment for all skills
      setStage('assessing');
      try {
        const skillsResp = await fetch(`${API_BASE_URL}/skills?limit=50`, {
          headers: authHeaders,
        });
        if (skillsResp.ok) {
          const skillsData = await skillsResp.json();
          const skillsList = skillsData.items || [];
          setAssessProgress({ done: 0, total: skillsList.length });

          const BATCH = 3;
          for (let i = 0; i < skillsList.length; i += BATCH) {
            const batch = skillsList.slice(i, i + BATCH);
            await Promise.allSettled(
              batch.map((skill: { skill_id: string }) =>
                fetch(`${API_BASE_URL}/bff/student/ai/demonstration`, {
                  method: 'POST',
                  headers: { ...authHeaders, 'Content-Type': 'application/json' },
                  body: JSON.stringify({ skill_id: skill.skill_id, doc_id: docId, k: 5 }),
                })
              )
            );
            setAssessProgress(prev => ({ ...prev, done: Math.min(i + BATCH, skillsList.length) }));
          }
        }
      } catch {
        // non-fatal: assessment errors don't block upload success
      }

      setStage('done');
      addToast('success', t('upload.success') || 'Document uploaded and assessed successfully.');
      setFile(null);
      setPurpose('');
      setScope('');
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('upload.failed');
      setError(msg);
      addToast('error', msg);
    } finally {
      setUploading(false);
    }
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    const icons: Record<string, string> = {
      // 文档
      pdf: '📕',
      docx: '📘',
      doc: '📘',
      txt: '📄',
      rtf: '📄',
      odt: '📄',
      md: '📝',
      markdown: '📝',
      // 表格
      xlsx: '📊',
      xls: '📊',
      csv: '📊',
      // 演示
      pptx: '📽️',
      ppt: '📽️',
      // 图片
      jpg: '🖼️',
      jpeg: '🖼️',
      png: '🖼️',
      webp: '🖼️',
      gif: '🖼️',
      bmp: '🖼️',
      tiff: '🖼️',
      tif: '🖼️',
      svg: '🖼️',
      heic: '🖼️',
      // 视频
      mp4: '🎬',
      webm: '🎬',
      mov: '🎬',
      avi: '🎬',
      mkv: '🎬',
      // 音频
      mp3: '🎵',
      wav: '🎵',
      m4a: '🎵',
      ogg: '🎵',
      flac: '🎵',
      // 代码
      py: '🐍',
      ipynb: '📓',
      js: '💛',
      jsx: '💛',
      ts: '💙',
      tsx: '💙',
      java: '☕',
      cpp: '⚙️',
      c: '⚙️',
      go: '🔷',
      rs: '🦀',
      rb: '💎',
      php: '🐘',
      swift: '🍎',
      kt: '🟣',
      scala: '🔴',
      r: '📈',
      sql: '🗃️',
      sh: '🖥️',
      bash: '🖥️',
      json: '📋',
      yaml: '📋',
      yml: '📋',
      xml: '📋',
      html: '🌐',
      css: '🎨',
      scss: '🎨',
      vue: '💚',
      svelte: '🧡',
    };
    return icons[ext || ''] || '📄';
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="page">
      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <Link href="/" className="logo">
            <span>🎓</span>
            <span>SkillSight</span>
          </Link>
          <nav className="nav">
            <Link href="/" className="nav-link">{t('nav.home')}</Link>
            <Link href="/upload" className="nav-link active">{t('nav.upload')}</Link>
            <Link href="/assess" className="nav-link">{t('nav.assess')}</Link>
            <Link href="/profile" className="nav-link">{t('nav.dashboard')}</Link>
          </nav>
        </div>
      </header>

      <main className="main">
        <div className="container" style={{ maxWidth: '640px' }}>
          {/* Page Title */}
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <h1 style={{ marginBottom: '0.5rem' }}>{t('upload.title')}</h1>
            <p style={{ color: 'var(--gray-600)' }}>
              {t('upload.subtitle')}
            </p>
          </div>

          {/* Success Message */}
          {result && (
            <div className="alert alert-success fade-in" style={{ marginBottom: '1.5rem' }}>
              <span>✓</span>
              <div style={{ flex: 1 }}>
                <strong>{t('upload.success')}</strong>
                <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>
                  {t('upload.processed')} {result.chunks_created} {t('upload.chunks')}
                </p>
                <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                  <Link 
                    href={`/documents/${result.doc_id}`}
                    className="btn btn-primary btn-sm"
                  >
                    📋 {t('upload.viewDetails')}
                  </Link>
                  <Link 
                    href="/dashboard"
                    className="btn btn-ghost btn-sm"
                  >
                    {t('upload.backToDashboard')}
                  </Link>
                </div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="alert alert-error fade-in" style={{ marginBottom: '1.5rem' }}>
              <span>⚠</span>
              <div>
                <strong>{t('upload.failed')}</strong>
                <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>{error}</p>
              </div>
            </div>
          )}

          {/* Refusal UX */}
          {refusal && (
            <div className="alert fade-in" style={{
              marginBottom: '1.5rem',
              background: '#fff8e6',
              border: '1px solid #f5d66e',
              borderRadius: '12px',
              padding: '1rem 1.25rem',
              display: 'flex',
              gap: '0.75rem',
            }}>
              <span style={{ fontSize: '1.25rem' }}>⚠️</span>
              <div>
                <strong style={{ color: '#8a6d00' }}>{t('upload.rejected')}{refusal.code}</strong>
                <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem', color: '#5a4900' }}>
                  {refusal.message}
                </p>
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.813rem', color: '#6b5700', fontWeight: 500 }}>
                  {t('upload.nextStep')}{refusal.next_step}
                </p>
              </div>
            </div>
          )}

          {/* Upload Card */}
          <div className="card">
            <div className="card-content">
              {/* Drop Zone */}
              <div
                className={`upload-zone ${dragActive ? 'active' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                  accept=".txt,.doc,.docx,.pdf,.pptx,.ppt,.rtf,.odt,.md,.markdown,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.webp,.bmp,.tiff,.tif,.gif,.svg,.ico,.heic,.heif,.mp4,.webm,.mov,.avi,.mkv,.flv,.wmv,.mp3,.wav,.m4a,.ogg,.flac,.aac,.py,.pyw,.pyi,.ipynb,.js,.jsx,.ts,.tsx,.mjs,.cjs,.vue,.svelte,.html,.htm,.css,.scss,.sass,.less,.java,.cpp,.cc,.cxx,.c,.h,.hpp,.cs,.go,.rs,.rb,.php,.swift,.kt,.kts,.scala,.r,.R,.m,.mm,.sh,.bash,.zsh,.fish,.ps1,.bat,.cmd,.json,.yaml,.yml,.xml,.toml,.ini,.cfg,.conf,.env,.sql,.lua,.pl,.pm,.ex,.exs,.erl,.hrl,.clj,.cljs,.hs,.lhs,.elm,.dart,.groovy,.gradle,.tf,.proto,.graphql,.gql,.log,.diff,.patch"
                />
                
                {file ? (
                  <div>
                    <div className="upload-zone-icon">{getFileIcon(file.name)}</div>
                    <div style={{ fontWeight: 600, color: 'var(--gray-900)', marginBottom: '0.25rem' }}>
                      {file.name}
                    </div>
                    <div className="upload-zone-text">
                      {formatFileSize(file.size)} · {t('upload.clickToChange')}
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="upload-zone-icon">📄</div>
                    <div className="upload-zone-text">
                      <strong>{t('upload.dropHere')}</strong>
                      <br />
                      {t('upload.orClick')}
                    </div>
                  </div>
                )}
              </div>

              {/* Supported Formats */}
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: '0.75rem', 
                marginTop: '1.25rem',
                padding: '1rem',
                background: 'var(--gray-50)',
                borderRadius: '12px'
              }}>
                {supportedFormats.map((format) => (
                  <div 
                    key={format.categoryKey}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '0.5rem',
                      fontSize: '0.8rem'
                    }}
                  >
                    <span style={{ fontSize: '1rem' }}>{format.icon}</span>
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--gray-700)', marginBottom: '0.125rem' }}>
                        {t(format.categoryKey)}
                      </div>
                      <div style={{ color: 'var(--gray-500)', fontSize: '0.7rem', lineHeight: 1.3 }}>
                        {format.formats}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Consent: Purpose + Scope (mandatory) */}
              <div style={{
                borderTop: '1px solid var(--gray-100)',
                marginTop: '1.5rem',
                paddingTop: '1.5rem',
              }}>
                <div style={{ marginBottom: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>
                  {t('upload.consentTitle')}
                </div>
                <p style={{ fontSize: '0.813rem', color: 'var(--gray-500)', marginBottom: '1rem' }}>
                  {t('upload.consentDesc')}
                </p>

                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--gray-700)', display: 'block', marginBottom: '0.375rem' }}>
                    {t('upload.purpose')} <span style={{ color: '#e53e3e' }}>*</span>
                  </label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {PURPOSE_KEYS.map(p => (
                      <label key={p.value} style={{
                        display: 'flex', alignItems: 'flex-start', gap: '0.625rem',
                        padding: '0.625rem 0.875rem',
                        borderRadius: '8px',
                        border: `1.5px solid ${purpose === p.value ? 'var(--primary)' : 'var(--gray-200)'}`,
                        background: purpose === p.value ? 'var(--primary-light, #fef0f0)' : 'white',
                        cursor: 'pointer',
                      }}>
                        <input
                          type="radio"
                          name="purpose"
                          value={p.value}
                          checked={purpose === p.value}
                          onChange={() => setPurpose(p.value)}
                          style={{ marginTop: '2px', accentColor: 'var(--primary)' }}
                        />
                        <div>
                          <div style={{ fontWeight: 500, fontSize: '0.875rem', color: 'var(--gray-900)' }}>{t(p.labelKey)}</div>
                          <div style={{ fontSize: '0.775rem', color: 'var(--gray-500)' }}>{t(p.descKey)}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--gray-700)', display: 'block', marginBottom: '0.375rem' }}>
                    {t('upload.scope')} <span style={{ color: '#e53e3e' }}>*</span>
                  </label>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {SCOPE_KEYS.map(s => (
                      <label key={s.value} style={{
                        flex: '1 1 auto',
                        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.25rem',
                        padding: '0.625rem 0.875rem',
                        borderRadius: '8px',
                        border: `1.5px solid ${scope === s.value ? 'var(--primary)' : 'var(--gray-200)'}`,
                        background: scope === s.value ? 'var(--primary-light, #fef0f0)' : 'white',
                        cursor: 'pointer',
                        textAlign: 'center',
                      }}>
                        <input
                          type="radio"
                          name="scope"
                          value={s.value}
                          checked={scope === s.value}
                          onChange={() => setScope(s.value)}
                          style={{ accentColor: 'var(--primary)' }}
                        />
                        <div style={{ fontWeight: 500, fontSize: '0.8rem', color: 'var(--gray-900)' }}>{t(s.labelKey)}</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--gray-500)' }}>{t(s.descKey)}</div>
                      </label>
                    ))}
                  </div>
                </div>

                {consentComplete && (
                  <div style={{
                    marginTop: '0.875rem',
                    padding: '0.625rem 0.875rem',
                    background: 'var(--sage-light, #f0f7f4)',
                    borderRadius: '8px',
                    fontSize: '0.813rem',
                    color: '#276749',
                  }}>
                    {t('upload.consentGranted')}{t(PURPOSE_KEYS.find(p => p.value === purpose)!.labelKey)}{t('upload.consentScope')}{t(SCOPE_KEYS.find(s => s.value === scope)!.labelKey)}{t('upload.consentRevoke')}
                  </div>
                )}
              </div>

              {/* Upload Button */}
              <button
                className="btn btn-primary btn-lg"
                style={{ width: '100%', marginTop: '1.5rem' }}
                onClick={handleUpload}
                disabled={!file || !consentComplete || uploading}
              >
                {uploading ? (
                  <>
                    <div className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></div>
                    {stage === 'uploading' && (t('upload.processing'))}
                    {stage === 'embedding' && (language === 'en' ? 'Generating embeddings...' : language === 'zh-TW' ? '正在生成向量...' : '正在生成向量...')}
                    {stage === 'assessing' && (language === 'en' ? `AI assessing skills (${assessProgress.done}/${assessProgress.total})...` : language === 'zh-TW' ? `AI 評估技能中 (${assessProgress.done}/${assessProgress.total})...` : `AI 评估技能中 (${assessProgress.done}/${assessProgress.total})...`)}
                    {stage === 'done' && (language === 'en' ? 'Complete!' : '完成！')}
                  </>
                ) : (
                  <>📤 {t('upload.button')}</>
                )}
              </button>
            </div>
          </div>

          {/* Info Card */}
          <div className="card" style={{ marginTop: '1.5rem' }}>
            <div className="card-content">
              <h3 style={{ fontSize: '1rem', marginBottom: '1rem' }}>{t('upload.tipsTitle')}</h3>
              <ul style={{ 
                color: 'var(--gray-600)', 
                fontSize: '0.875rem',
                listStyle: 'none',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem'
              }}>
                <li>{t('upload.tip1')}</li>
                <li>{t('upload.tip2')}</li>
                <li>{t('upload.tip3')}</li>
                <li>{t('upload.tip4')}</li>
              </ul>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer style={{ 
        padding: '1.5rem', 
        textAlign: 'center', 
        borderTop: '1px solid var(--gray-200)',
        color: 'var(--gray-500)',
        fontSize: '0.875rem'
      }}>
        <p>© 2026 SkillSight · HKU Skills-to-Jobs Transparency System</p>
      </footer>
    </div>
  );
}
