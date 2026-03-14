'use client';

import { useEffect, useRef, useState } from 'react';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { studentBff, getToken } from '@/lib/bffClient';
import styles from './resume.module.css';

const ACCEPTED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10MB

interface DocItem {
  doc_id: string;
  filename: string;
  created_at?: string;
  doc_type?: string;
}

interface RoleItem {
  role_id?: string;
  role_title?: string;
}

interface ResumeUploaderProps {
  onStart: (reviewId: string, docId: string, targetRoleId?: string) => void;
  existingReviewId?: string | null;
}

export function ResumeUploader({ onStart, existingReviewId }: ResumeUploaderProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [targetRoleId, setTargetRoleId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type) && !file.name.toLowerCase().match(/\.(pdf|docx)$/)) {
      return (typeof t('resume.uploadFileTypeError') === 'string' ? t('resume.uploadFileTypeError') : 'Please upload a PDF or DOCX file.');
    }
    if (file.size > MAX_FILE_BYTES) {
      return (typeof t('resume.uploadFileSizeError') === 'string' ? t('resume.uploadFileSizeError') : 'File must be under 10MB.');
    }
    return null;
  };

  const uploadFile = async (file: File) => {
    const err = validateFile(file);
    if (err) {
      addToast('error', err);
      return;
    }
    setUploading(true);
    try {
      const token = getToken()!;
      const uploadRes = await studentBff.upload(file, 'skill_assessment', 'full', token);
      const docId = (uploadRes as { doc_id?: string }).doc_id;
      if (docId) {
        setDocs(prev => [{ doc_id: docId, filename: file.name, created_at: new Date().toISOString() }, ...prev]);
        setSelectedDocId(docId);
        addToast('success', (t('resume.uploadSuccess') as string) || 'Uploaded');
      }
    } catch {
      addToast('error', (t('common.error') as string) || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    const load = async () => {
      if (!getToken()) return;
      setLoading(true);
      try {
        const [docRes, roleRes] = await Promise.all([
          studentBff.getDocuments(50),
          studentBff.getRoles(100),
        ]);
        setDocs((docRes as { items: DocItem[] }).items || []);
        setRoles((roleRes as { items: RoleItem[] }).items || []);
      } catch {
        setDocs([]);
        setRoles([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleStartReview = async () => {
    if (!selectedDocId) {
      addToast('error', (t('resume.selectDocHint') as string) || 'Please select a document');
      return;
    }
    setStarting(true);
    try {
      const res = await studentBff.resumeReviewStart(
        selectedDocId,
        targetRoleId || undefined
      );
      onStart(res.review_id, selectedDocId, targetRoleId || undefined);
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? String((e as { message: string }).message) : 'Failed to start review';
      addToast('error', msg);
    } finally {
      setStarting(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const files = e.dataTransfer?.files;
    if (!files?.length || !getToken()) return;
    await uploadFile(files[0]);
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && getToken()) void uploadFile(file);
    e.target.value = '';
  };

  const handleUploadZoneKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const handleDocKeyDown = (e: React.KeyboardEvent<HTMLLIElement>, doc: DocItem) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setSelectedDocId(selectedDocId === doc.doc_id ? null : doc.doc_id);
    }
  };

  if (loading) {
    return (
      <div className={styles.stepContent}>
        <p>{t('common.loading') || 'Loading...'}</p>
      </div>
    );
  }

  return (
    <>
      <h2 className={styles.pageTitle} style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step1Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '1rem', fontSize: '0.9375rem' }}>{t('resume.step1Desc')}</p>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        style={{ position: 'absolute', width: 1, height: 1, opacity: 0, overflow: 'hidden', clip: 'rect(0,0,0,0)' }}
        aria-label={t('resume.uploadNew')}
        onChange={handleFileInputChange}
      />
      <div
        role="button"
        tabIndex={0}
        className={`${styles.uploadZone} ${dragActive || uploading ? styles.uploadZoneActive : ''}`}
        onDragEnter={() => setDragActive(true)}
        onDragLeave={() => setDragActive(false)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={handleUploadZoneKeyDown}
        aria-label={t('resume.dragHint')}
      >
        <p style={{ margin: 0, color: 'var(--gray-600)' }}>{t('resume.dragHint')}</p>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('resume.uploadNew')}</p>
      </div>

      <p style={{ margin: '1.5rem 0 0.5rem', fontWeight: 600 }}>{t('resume.orSelectExisting')}</p>
      <ul className={styles.docList} role="listbox" aria-label={t('resume.selectDoc')}>
        {docs.length === 0 ? (
          <li style={{ color: 'var(--gray-500)', padding: '1rem' }}>{t('resume.noDocuments')}</li>
        ) : (
          docs.map((d) => (
            <li
              key={d.doc_id}
              role="option"
              tabIndex={0}
              aria-selected={selectedDocId === d.doc_id}
              className={`${styles.docItem} ${selectedDocId === d.doc_id ? styles.docItemSelected : ''}`}
              onClick={() => setSelectedDocId(selectedDocId === d.doc_id ? null : d.doc_id)}
              onKeyDown={(e) => handleDocKeyDown(e, d)}
            >
              <span>{d.filename}</span>
              {d.created_at && (
                <span style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
                  {new Date(d.created_at).toLocaleDateString()}
                </span>
              )}
            </li>
          ))
        )}
      </ul>

      <div style={{ marginTop: '1.5rem' }}>
        <label htmlFor="resume-target-role" style={{ display: 'block', marginBottom: '0.35rem', fontSize: '0.875rem' }}>
          {t('resume.selectTargetRole')}
        </label>
        {roles.length === 0 ? (
          <p style={{ color: 'var(--gray-500)', fontSize: '0.875rem', margin: 0 }}>
            {t('resume.noTargetRoles') || '暂无目标岗位'}
          </p>
        ) : (
          <select
            id="resume-target-role"
            value={targetRoleId}
            onChange={(e) => setTargetRoleId(e.target.value)}
            style={{ padding: '0.5rem 0.75rem', borderRadius: 'var(--radius)', border: '1px solid var(--gray-200)', minWidth: '200px' }}
          >
            <option value="">{t('resume.optional') || '—'}</option>
            {roles.map((r, idx) => (
              <option key={r.role_id ?? `role-${idx}`} value={r.role_id || ''}>{r.role_title || r.role_id}</option>
            ))}
          </select>
        )}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleStartReview}
          disabled={!selectedDocId || starting}
        >
          {starting ? (t('common.loading') || '...') : t('resume.startReview')}
        </button>
      </div>
    </>
  );
}
