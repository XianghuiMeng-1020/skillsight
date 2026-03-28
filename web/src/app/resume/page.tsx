'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/lib/contexts';

/** Redirect /resume -> /dashboard/resume for backwards compatibility / bookmarks. */
export default function ResumeRedirect() {
  const router = useRouter();
  const { t } = useLanguage();
  useEffect(() => {
    router.replace('/dashboard/resume');
  }, [router]);
  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <p>{t('redirect.resume')}</p>
    </div>
  );
}
