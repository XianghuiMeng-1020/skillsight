'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/lib/contexts';

/** Redirect /jobs -> /dashboard/jobs for backwards compatibility / bookmarks. */
export default function JobsRedirect() {
  const router = useRouter();
  const { t } = useLanguage();
  useEffect(() => {
    router.replace('/dashboard/jobs');
  }, [router]);
  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <p>{t('redirect.jobs')}</p>
    </div>
  );
}
