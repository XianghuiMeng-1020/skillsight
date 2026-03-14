'use client';

import { useEffect, useState } from 'react';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { studentBff, getToken } from '@/lib/bffClient';
import styles from './resume.module.css';

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
    const file = files[0];
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
    } catch (err) {
      addToast('error', (t('common.error') as string) || 'Upload failed');
    } finally {
      setUploading(false);
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

      <div
        className={`${styles.uploadZone} ${dragActive || uploading ? styles.uploadZoneActive : ''}`}
        onDragEnter={() => setDragActive(true)}
        onDragLeave={() => setDragActive(false)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        <p style={{ margin: 0, color: 'var(--gray-600)' }}>{t('resume.dragHint')}</p>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('resume.uploadNew')}</p>
      </div>

      <p style={{ margin: '1.5rem 0 0.5rem', fontWeight: 600 }}>{t('resume.orSelectExisting')}</p>
      <ul className={styles.docList}>
        {docs.length === 0 ? (
          <li style={{ color: 'var(--gray-500)', padding: '1rem' }}>{t('resume.noDocuments') || 'No documents yet. Upload a resume first.'}</li>
        ) : (
          docs.map((d) => (
            <li
              key={d.doc_id}
              className={`${styles.docItem} ${selectedDocId === d.doc_id ? styles.docItemSelected : ''}`}
              onClick={() => setSelectedDocId(selectedDocId === d.doc_id ? null : d.doc_id)}
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
        <select
          id="resume-target-role"
          value={targetRoleId}
          onChange={(e) => setTargetRoleId(e.target.value)}
          style={{ padding: '0.5rem 0.75rem', borderRadius: 'var(--radius)', border: '1px solid var(--gray-200)', minWidth: '200px' }}
        >
          <option value="">—</option>
          {roles.map((r) => (
            <option key={r.role_id || ''} value={r.role_id || ''}>{r.role_title || r.role_id}</option>
          ))}
        </select>
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
