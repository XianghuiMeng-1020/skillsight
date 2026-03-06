'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { FullLearningPath } from '@/components/LearningPath';
import { useLanguage } from '@/lib/contexts';
import { getToken, studentBff } from '@/lib/bffClient';

interface SkillEntry {
  canonical_name?: string;
  level?: number;
}

interface ProfileData {
  skills?: SkillEntry[];
}

export default function LearningPage() {
  const { t } = useLanguage();
  const [skills, setSkills] = useState<Array<{ name: string; level: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        if (!getToken()) {
          if (!cancelled) setSkills([]);
          return;
        }
        const profile = (await studentBff.getProfile()) as ProfileData;
        const mapped = (profile.skills || [])
          .map((s) => ({
            name: s.canonical_name || t('common.unknown'),
            level: typeof s.level === 'number' ? s.level : 0,
          }))
          .filter((s) => s.name.trim().length > 0);
        if (!cancelled) setSkills(mapped);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load learning data');
          setSkills([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [t]);

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
          {loading ? (
            <div className="loading">
              <span className="spinner"></span>
              {t('common.loading')}
            </div>
          ) : error ? (
            <div className="alert alert-error">
              <span>⚠</span>
              <div>
                <strong>{t('common.loadFailed')}</strong>
                <p style={{ marginTop: '0.25rem', fontSize: '0.875rem' }}>{error}</p>
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
