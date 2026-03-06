'use client';

import { ReactNode } from 'react';
import { ThemeProvider, LanguageProvider, TutorialProvider } from '@/lib/contexts';
import { TutorialOverlay } from '@/components/Tutorial';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <TutorialProvider>
          {children}
          <TutorialOverlay />
        </TutorialProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
