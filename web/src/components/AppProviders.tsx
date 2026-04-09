'use client';

import { ReactNode } from 'react';
import { ThemeProvider, LanguageProvider, TutorialProvider } from '@/lib/contexts';
import { TutorialOverlay } from '@/components/Tutorial';
import { SWRConfig } from 'swr';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <TutorialProvider>
          <SWRConfig
            value={{
              revalidateOnFocus: false,
              dedupingInterval: 30_000,
              focusThrottleInterval: 10_000,
            }}
          >
            {children}
            <TutorialOverlay />
          </SWRConfig>
        </TutorialProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
