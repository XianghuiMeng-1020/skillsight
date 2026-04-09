'use client';

import useSWR, { type SWRConfiguration } from 'swr';
import { studentBff, getToken, type ProfileResponse } from '@/lib/bffClient';

const DEFAULT_SWR_OPTIONS: SWRConfiguration = {
  revalidateOnFocus: false,
  dedupingInterval: 30_000,
  focusThrottleInterval: 10_000,
};

type UseProfileOptions = {
  enabled?: boolean;
  config?: SWRConfiguration<ProfileResponse>;
};

export function useProfileSWR(options: UseProfileOptions = {}) {
  const enabled = options.enabled ?? true;
  const canFetch = enabled && !!getToken();
  return useSWR<ProfileResponse>(
    canFetch ? ['profile', 'student'] : null,
    () => studentBff.getProfile(),
    { ...DEFAULT_SWR_OPTIONS, ...(options.config || {}) }
  );
}

export function useRolesSWR(limit = 20, enabled = true) {
  const canFetch = enabled && !!getToken();
  return useSWR<{ items: unknown[] }>(
    canFetch ? ['roles', limit] : null,
    () => studentBff.getRoles(limit),
    DEFAULT_SWR_OPTIONS
  );
}

export function useDocumentsSWR(limit = 20, enabled = true) {
  const canFetch = enabled && !!getToken();
  return useSWR<{ items: unknown[]; count: number }>(
    canFetch ? ['documents', limit] : null,
    () => studentBff.getDocuments(limit),
    DEFAULT_SWR_OPTIONS
  );
}
