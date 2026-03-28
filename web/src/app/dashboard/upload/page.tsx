'use client';

import Link from 'next/link';
import { useState, useRef, DragEvent } from 'react';
import Sidebar from '@/components/Sidebar';
import { useToast } from '@/components/Toast';
import { studentBff, getToken } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';

interface UploadResult {
  doc_id: string;
  filename: string;
  chunks_created: number;
}

const ACCEPTED_FILE_TYPES = [
  '.txt', '.doc', '.docx', '.pdf', '.pptx', '.ppt', '.rtf', '.odt', '.md', '.markdown', '.mdx',
  '.tex', '.latex', '.epub',
  '.xlsx', '.xls', '.csv',
  '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif', '.gif', '.svg', '.ico', '.heic', '.heif',
  '.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac',
  '.zip',
  '.py', '.pyw', '.pyi', '.ipynb',
  '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.vue', '.svelte',
  '.html', '.htm', '.css', '.scss', '.sass', '.less',
  '.java', '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.kts', '.scala', '.r', '.R', '.m', '.mm',
  '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
  '.json', '.yaml', '.yml', '.xml', '.toml', '.ini', '.cfg', '.conf', '.env', '.sql',
  '.lua', '.pl', '.pm', '.ex', '.exs', '.erl', '.hrl', '.clj', '.cljs', '.hs', '.lhs', '.elm', '.dart', '.groovy', '.gradle', '.tf', '.proto', '.graphql', '.gql',
  '.log', '.diff', '.patch',
].join(',');

export default function UploadPage() {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const [consent, setConsent] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ current: 0, total: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const supportedFormats = [
    { ext: 'Docs', icon: '📄', desc: 'PDF, DOCX, PPTX, MD, RTF, ODT, LaTeX, EPUB' },
    { ext: 'Spreadsheets', icon: '📊', desc: 'XLSX, XLS, CSV' },
    { ext: 'Images', icon: '🖼️', desc: 'JPG, PNG, WEBP, SVG, HEIC' },
    { ext: 'Media', icon: '🎬', desc: 'MP4, WEBM, MP3, WAV, AAC' },
    { ext: 'Notebook', icon: '📓', desc: 'IPYNB' },
    { ext: 'Code', icon: '💻', desc: 'Python, JS/TS, Java, C/C++, Go, Rust, PHP...' },
    { ext: 'Config', icon: '⚙️', desc: 'JSON, YAML, TOML, XML, ENV, SQL' },
    { ext: 'Archive', icon: '📦', desc: 'ZIP (auto-extracts and parses contents)' },
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
    
    if (e.dataTransfer.files) {
      const newFiles = Array.from(e.dataTransfer.files);
      setFiles(prev => [...prev, ...newFiles]);
      setError(null);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...newFiles]);
      setError(null);
    }
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (files.length === 0 || !consent) return;

    const token = getToken();
    if (!token) {
      setError(t('upload.loginRequired'));
      return;
    }

    setUploading(true);
    setError(null);
    setResults([]);
    setUploadProgress({ current: 0, total: files.length });

    try {
      const uploadResults: UploadResult[] = [];

      for (let i = 0; i < files.length; i++) {
        setUploadProgress({ current: i + 1, total: files.length });
        const data = await studentBff.upload(files[i], 'skill_assessment', 'full', token);
        uploadResults.push(data);
      }

      setResults(uploadResults);
      setFiles([]);
      setConsent(false);

      // Trigger auto-assess for each uploaded document
      const docIds = uploadResults.map((r) => r.doc_id).filter(Boolean);
      if (docIds.length > 0) {
        setTimeout(async () => {
          let ok = 0;
          let fail = 0;
          for (const docId of docIds) {
            try {
              const r = await studentBff.autoAssessDocument(docId);
              if (r?.status === 'accepted') ok += 1;
              else fail += 1;
            } catch {
              fail += 1;
            }
          }
          if (ok === docIds.length) {
            addToast('success', (t('upload.autoAssessDone') as string)?.replace('{n}', String(ok)) ?? `Queued assessment for ${ok} document(s).`);
          } else if (ok > 0) {
            addToast(
              'warning',
              (t('upload.autoAssessPartial') as string)?.replace('{ok}', String(ok)).replace('{fail}', String(fail)) ?? `${ok} queued, ${fail} failed.`
            );
          } else {
            addToast('error', (t('upload.autoAssessAllFailed') as string) ?? 'Auto-assess failed to start.');
          }
        }, 2000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('upload.failed'));
    } finally {
      setUploading(false);
      setUploadProgress({ current: 0, total: 0 });
    }
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    const icons: Record<string, string> = {
      pdf: '📕', docx: '📘', doc: '📘', txt: '📄', pptx: '📊', ppt: '📊',
      jpg: '🖼️', jpeg: '🖼️', png: '🖼️', mp4: '🎬', mp3: '🎵',
      py: '🐍', js: '💛', ts: '💙', java: '☕', cpp: '⚙️',
    };
    return icons[ext || ''] || '📄';
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('dashboard.uploadEvidence')}</h1>
            <p className="page-subtitle">{t('upload.pageSubtitle')}</p>
          </div>
        </div>

        <div className="page-content">
          <div className="alert" style={{ marginBottom: '1rem', border: '1px solid var(--gray-200)' }}>
            <span className="alert-icon">🌟</span>
            <div className="alert-content">
              <div className="alert-title">{t('upload.demoRouteTitle')}</div>
              <p>{t('upload.demoRouteDesc')}</p>
              <p style={{ marginTop: '0.4rem', fontSize: '0.875rem', color: 'var(--gray-500)' }}>
                1) {t('dashboard.uploadEvidence')} → 2) {t('dashboard.takeAssessment')} → 3) {t('dashboard.skills')} → 4) {t('dashboard.findJobs')}
              </p>
            </div>
          </div>

          {/* Success Message */}
          {results.length > 0 && (
            <div className="alert alert-success fade-in">
              <span className="alert-icon">✓</span>
              <div className="alert-content">
                <div className="alert-title">{t('upload.success')}</div>
                <p>{results.length} {t('upload.filesProcessedSuccess')}</p>
                <p style={{ marginTop: '0.5rem', fontSize: '0.8125rem', color: 'var(--gray-600)' }}>
                  {t('upload.autoAssessHint')}
                </p>
                <ul style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>
                  {results.map((r, i) => (
                    <li key={i}>&quot;{r.filename}&quot; - {r.chunks_created} {t('upload.sectionsExtracted')}</li>
                  ))}
                </ul>
                <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <Link href="/dashboard/skills" className="btn btn-sm btn-ghost">{t('upload.nextViewSkills')}</Link>
                  <Link href="/dashboard/jobs" className="btn btn-sm btn-ghost">{t('upload.nextViewJobs')}</Link>
                </div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="alert alert-error fade-in">
              <span className="alert-icon">⚠</span>
              <div className="alert-content">
                <div className="alert-title">{t('upload.failed')}</div>
                <p>{error}</p>
                {!getToken() && (
                  <a
                    href="/login"
                    style={{
                      display: 'inline-block',
                      marginTop: '0.5rem',
                      padding: '0.375rem 0.75rem',
                      borderRadius: '8px',
                      background: 'var(--hku-green)',
                      color: 'white',
                      fontWeight: 500,
                      fontSize: '0.875rem',
                      textDecoration: 'none',
                    }}
                  >
                    {t('upload.goToLogin')}
                  </a>
                )}
              </div>
            </div>
          )}

          {/* Suggested Uploads Card */}
          <div className="card" style={{ marginBottom: '1rem' }}>
            <div className="card-header">
              <h3 className="card-title">{t('upload.suggestedTitle')}</h3>
            </div>
            <div className="card-content">
              <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '1rem' }}>
                {t('upload.suggestedSubtitle')}
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                <div style={{ padding: '1rem', background: 'var(--hku-green-50)', borderRadius: 'var(--radius)', border: '1px solid var(--hku-green)' }}>
                  <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>📚</div>
                  <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.25rem' }}>{t('upload.suggestedCourseOutline')}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{t('upload.suggestedCourseOutlineDesc')}</div>
                </div>
                <div style={{ padding: '1rem', background: 'var(--warning-light)', borderRadius: 'var(--radius)', border: '1px solid var(--warning)' }}>
                  <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>📝</div>
                  <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.25rem' }}>{t('upload.suggestedAssignments')}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{t('upload.suggestedAssignmentsDesc')}</div>
                </div>
                <div style={{ padding: '1rem', background: 'var(--info-light)', borderRadius: 'var(--radius)', border: '1px solid var(--info)' }}>
                  <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>📄</div>
                  <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.25rem' }}>{t('upload.suggestedCV')}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{t('upload.suggestedCVDesc')}</div>
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
            {/* Main Upload Area */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">{t('upload.selectFiles')}</h3>
              </div>
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
                    multiple
                    onChange={handleFileSelect}
                    style={{ display: 'none' }}
                    accept={ACCEPTED_FILE_TYPES}
                  />
                  
                  <div className="upload-zone-icon">📁</div>
                  <div className="upload-zone-text">
                    {t('upload.dropOrBrowse')}
                  </div>
                  <div className="upload-zone-hint">
                    {t('upload.maxFileSize')}
                  </div>
                </div>

                {/* Supported Formats */}
                <div style={{ marginTop: '1.5rem' }}>
                  <div style={{ fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.75rem' }}>
                    {t('upload.supportedFormats')}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                    {supportedFormats.map((format) => (
                      <span 
                        key={format.ext}
                        className="badge badge-neutral"
                        title={format.desc}
                        style={{ cursor: 'help' }}
                      >
                        {format.icon} {format.ext}
                      </span>
                    ))}
                  </div>
                </div>

                {/* File List */}
                {files.length > 0 && (
                  <div style={{ marginTop: '1.5rem' }}>
                    <div style={{ fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.75rem' }}>
                      {t('upload.selectedFiles')} ({files.length}):
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {files.map((file, index) => (
                        <div 
                          key={`${file.name}-${file.size}-${index}`}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '0.75rem',
                            background: 'var(--gray-50)',
                            borderRadius: 'var(--radius)',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span style={{ fontSize: '1.25rem' }}>{getFileIcon(file.name)}</span>
                            <div>
                              <div style={{ fontWeight: 500 }}>{file.name}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                                {formatSize(file.size)}
                              </div>
                            </div>
                          </div>
                          <button 
                            className="btn btn-ghost btn-sm"
                            onClick={() => removeFile(index)}
                          >
                            ✕
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Consent Checkbox */}
                <div style={{ 
                  borderTop: '1px solid var(--gray-200)', 
                  marginTop: '1.5rem', 
                  paddingTop: '1.5rem' 
                }}>
                  <label className="checkbox-wrapper">
                    <input
                      type="checkbox"
                      className="checkbox"
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                    />
                    <div>
                      <span style={{ fontWeight: 500 }}>
                        {t('upload.consentCheckbox')}
                      </span>
                      <p style={{ fontSize: '0.813rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                        {t('upload.consentWithdraw')}
                      </p>
                    </div>
                  </label>
                </div>

                {/* Upload Button */}
                <button
                  className="btn btn-primary btn-lg"
                  style={{ width: '100%', marginTop: '1.5rem' }}
                  onClick={handleUpload}
                  disabled={files.length === 0 || !consent || uploading}
                >
                  {uploading ? (
                    <>
                      <span className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></span>
                      {uploadProgress.total > 1
                        ? `${t('upload.processing')} (${uploadProgress.current}/${uploadProgress.total})`
                        : t('upload.processing')}
                    </>
                  ) : (
                    <>{files.length > 0 ? t('upload.uploadNFiles').replace('{n}', String(files.length)) : t('upload.uploadFiles')}</>
                  )}
                </button>
              </div>
            </div>

            {/* Tips Sidebar */}
            <div>
              <div className="card">
                <div className="card-header">
                  <h3 className="card-title">{t('upload.tipsTitleResults')}</h3>
                </div>
                <div className="card-content">
                  <ul style={{ 
                    listStyle: 'none', 
                    display: 'flex', 
                    flexDirection: 'column', 
                    gap: '1rem',
                    fontSize: '0.875rem',
                    color: 'var(--gray-600)'
                  }}>
                    <li style={{ display: 'flex', gap: '0.75rem' }}>
                      <span>✓</span>
                      <span>{t('upload.tip1page')}</span>
                    </li>
                    <li style={{ display: 'flex', gap: '0.75rem' }}>
                      <span>✓</span>
                      <span>{t('upload.tip2page')}</span>
                    </li>
                    <li style={{ display: 'flex', gap: '0.75rem' }}>
                      <span>✓</span>
                      <span>{t('upload.tip3page')}</span>
                    </li>
                    <li style={{ display: 'flex', gap: '0.75rem' }}>
                      <span>✓</span>
                      <span>{t('upload.tip4page')}</span>
                    </li>
                  </ul>
                </div>
              </div>

              <div className="card" style={{ marginTop: '1rem' }}>
                <div className="card-header">
                  <h3 className="card-title">{t('upload.privacyCardTitle')}</h3>
                </div>
                <div className="card-content">
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '1rem' }}>
                    {t('upload.privacyCardDesc')}
                  </p>
                  <a href="/settings/privacy" className="btn btn-ghost btn-sm" style={{ width: '100%' }}>
                    {t('upload.managePrivacy')}
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
