'use client';

import { useState, useEffect } from 'react';
import { getToken } from '@/lib/bffClient';

export type AuthState = 'checking' | 'authenticated' | 'unauthenticated';

export function useRequireAuth() {
  const [authState, setAuthState] = useState<AuthState>('checking');

  useEffect(() => {
    const token = getToken();
    setAuthState(token ? 'authenticated' : 'unauthenticated');
  }, []);

  return authState;
}
