'use client';

import { useEffect, useState } from 'react';
import { getToken } from '@/lib/bffClient';

export function useAuthGuard() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!getToken());

  useEffect(() => {
    const sync = () => setIsAuthenticated(!!getToken());
    sync();
    window.addEventListener('storage', sync);
    window.addEventListener('skillsight-login', sync as EventListener);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener('skillsight-login', sync as EventListener);
    };
  }, []);

  return { isAuthenticated };
}
