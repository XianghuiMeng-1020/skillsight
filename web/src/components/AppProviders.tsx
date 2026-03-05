'use client';

import { ReactNode } from 'react';
import { ThemeProvider, LanguageProvider, TutorialProvider } from '@/lib/contexts';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <TutorialProvider>
          {children}
        </TutorialProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
