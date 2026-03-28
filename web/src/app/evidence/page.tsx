'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/lib/contexts';

/** Redirect /evidence -> /dashboard/upload for backwards compatibility / bookmarks. */
export default function EvidenceRedirect() {
  const router = useRouter();
  const { t } = useLanguage();
  useEffect(() => {
    router.replace('/dashboard/upload');
  }, [router]);
  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <p>{t('redirect.evidence')}</p>
    </div>
  );
}
