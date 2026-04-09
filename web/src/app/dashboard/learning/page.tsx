'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { FullLearningPath } from '@/components/LearningPath';
import { useLanguage } from '@/lib/contexts';
import { useProfileSWR } from '@/lib/swrHooks';
import { useAuthGuard } from '@/lib/useAuthGuard';

interface SkillEntry {
  canonical_name?: string;
  level?: number;
}

interface ProfileData {
  skills?: SkillEntry[];
}

export default function LearningPage() {
  const { t } = useLanguage();
  const { isAuthenticated } = useAuthGuard();
  const { data: profile, isLoading, error } = useProfileSWR({ enabled: isAuthenticated });
  const skills = useMemo(() => {
    const source = (profile as ProfileData | undefined)?.skills || [];
    return source
      .map((s) => ({
        name: s.canonical_name || t('common.unknown'),
        level: typeof s.level === 'number' ? s.level : 0,
      }))
      .filter((s) => s.name.trim().length > 0);
  }, [profile, t]);
  const loading = isAuthenticated ? isLoading : false;
  const errorMessage = error instanceof Error ? error.message : null;

  const hasSkills = useMemo(() => skills.length > 0, [skills]);

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('learning.pathTitle')}</h1>
            <p className="page-subtitle">{t('learning.analyzing')}</p>
          </div>
          <div className="page-actions">
            <Link href="/dashboard" className="btn btn-ghost btn-sm">
              {t('common.back')}
            </Link>
          </div>
        </div>

        <div className="page-content">
          {!isAuthenticated ? (
            <div className="alert alert-warning">
              <span>🔐</span>
              <div>
                <strong>{t('upload.loginRequired')}</strong>
                <p style={{ marginTop: '0.25rem', fontSize: '0.875rem' }}>{t('common.retryAfterLogin')}</p>
                <Link href="/login" className="btn btn-primary btn-sm" style={{ marginTop: '0.5rem' }}>
                  {t('common.login')}
                </Link>
              </div>
            </div>
          ) : loading ? (
            <div className="loading">
              <span className="spinner"></span>
              {t('common.loading')}
            </div>
          ) : errorMessage ? (
            <div className="alert alert-error">
              <span>⚠</span>
              <div>
                <strong>{t('common.loadFailed')}</strong>
                <p style={{ marginTop: '0.25rem', fontSize: '0.875rem' }}>{errorMessage}</p>
              </div>
            </div>
          ) : hasSkills ? (
            <FullLearningPath skills={skills} />
          ) : (
            <div className="card">
              <div className="empty-state">
                <div className="empty-icon">🎯</div>
                <div className="empty-title">{t('learning.noSuggestions')}</div>
                <div className="empty-desc">{t('learning.uploadMore')}</div>
                <Link href="/dashboard/upload" className="btn btn-primary btn-sm">
                  {t('upload.uploadNow')}
                </Link>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
