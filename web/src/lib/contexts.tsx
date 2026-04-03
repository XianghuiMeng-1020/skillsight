'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { usePathname } from 'next/navigation';
import { translations, type Translations } from './translations';

// Re-export so downstream consumers who import from contexts still work
export { translations, type Translations };

// ==========================================
// 1. 主题上下文 (深色模式)
// ==========================================
type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('light');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const savedTheme = localStorage.getItem('skillsight-theme') as Theme;
      if (savedTheme) {
        setThemeState(savedTheme);
        document.documentElement.setAttribute('data-theme', savedTheme);
      } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        setThemeState('dark');
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    } catch (e) {
      console.warn('Failed to read theme from localStorage:', e);
    }
  }, []);

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    try {
      localStorage.setItem('skillsight-theme', newTheme);
    } catch (e) {
      console.warn('Failed to save theme to localStorage:', e);
    }
    document.documentElement.setAttribute('data-theme', newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  }, [theme, setTheme]);

  // Always provide context so useTheme() never throws (SSR-safe when !mounted)
  const value = mounted
    ? { theme, toggleTheme, setTheme }
    : { theme: 'light' as Theme, toggleTheme: () => {}, setTheme: () => {} };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

const defaultThemeContext: ThemeContextType = {
  theme: 'light',
  toggleTheme: () => {},
  setTheme: () => {},
};

export function useTheme() {
  const context = useContext(ThemeContext);
  return context ?? defaultThemeContext;
}

// ==========================================
// 2. 语言上下文 (多语言支持)
// ==========================================
export type Language = 'zh' | 'zh-TW' | 'en';

export const LANGUAGES: { value: Language; label: string; short: string }[] = [
  { value: 'zh', label: '简体中文', short: '简' },
  { value: 'zh-TW', label: '繁體中文', short: '繁' },
  { value: 'en', label: 'English', short: 'EN' },
];

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>('zh');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const savedLang = localStorage.getItem('skillsight-language') as Language;
      if (savedLang && ['zh', 'zh-TW', 'en'].includes(savedLang)) {
        setLanguageState(savedLang);
      }
    } catch (e) {
      console.warn('Failed to read language from localStorage:', e);
    }
  }, []);

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang);
    try {
      localStorage.setItem('skillsight-language', lang);
    } catch (e) {
      console.warn('Failed to save language to localStorage:', e);
    }
  }, []);

  useEffect(() => {
    const langAttr = language === 'zh' ? 'zh-CN' : language === 'zh-TW' ? 'zh-TW' : 'en';
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('lang', langAttr);
    }
  }, [language]);

  const t = useCallback((key: string): string => {
    const translation = translations[key];
    if (!translation) {
      if (process.env.NODE_ENV !== 'production') {
        console.warn(`Translation missing for key: ${key}`);
      }
      return key;
    }
    return translation[language] ?? translation['zh'];
  }, [language]);

  // Always provide context so useLanguage() never throws (SSR-safe when !mounted)
  const value = mounted
    ? { language, setLanguage, t }
    : {
        language: 'zh' as Language,
        setLanguage: (() => {}) as (lang: Language) => void,
        t: ((key: string) => translations[key]?.zh ?? key) as (key: string) => string,
      };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

const defaultLanguageContext: LanguageContextType = {
  language: 'zh',
  setLanguage: () => {},
  t: (key: string) => key, // SSR fallback; translations may not be ready
};

export function useLanguage() {
  const context = useContext(LanguageContext);
  return context ?? defaultLanguageContext;
}

// ==========================================
// 3. 引导教程上下文
// ==========================================
interface TutorialContextType {
  showTutorial: boolean;
  currentStep: number;
  totalSteps: number;
  tutorialName: string;
  setTutorialName: (name: string) => void;
  startTutorial: () => void;
  nextStep: () => void;
  prevStep: () => void;
  skipTutorial: () => void;
  completeTutorial: () => void;
}

const TutorialContext = createContext<TutorialContextType | undefined>(undefined);

export function TutorialProvider({ children }: { children: ReactNode }) {
  const [showTutorial, setShowTutorial] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [tutorialName, setTutorialNameState] = useState('');
  const totalSteps = 5;
  const pathname = usePathname();

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    try {
      const hasSeenTutorial = localStorage.getItem('skillsight-tutorial-completed');
      const user = localStorage.getItem('user');
      const savedName = localStorage.getItem('skillsight-onboarding-name');
      if (savedName) setTutorialNameState(savedName);
      const isDashboardOrHome = pathname === '/dashboard' || pathname === '/';
      if (!hasSeenTutorial && user && isDashboardOrHome) {
        timer = setTimeout(() => setShowTutorial(true), 800);
      }
    } catch (e) {
      console.warn('Failed to read tutorial state from localStorage:', e);
    }
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [pathname]);

  const setTutorialName = useCallback((name: string) => {
    const clean = name.trim();
    setTutorialNameState(clean);
    if (typeof localStorage !== 'undefined') {
      try {
        if (clean) localStorage.setItem('skillsight-onboarding-name', clean);
        else localStorage.removeItem('skillsight-onboarding-name');
      } catch (e) {
        console.warn('Failed to save tutorial name to localStorage:', e);
      }
    }
  }, []);

  const startTutorial = useCallback(() => {
    setCurrentStep(0);
    setShowTutorial(true);
  }, []);

  const nextStep = useCallback(() => {
    if (currentStep < totalSteps - 1) {
      setCurrentStep(prev => prev + 1);
    }
  }, [currentStep, totalSteps]);

  const prevStep = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1);
    }
  }, [currentStep]);

  const skipTutorial = useCallback(() => {
    setShowTutorial(false);
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem('skillsight-tutorial-completed', 'true');
      } catch (e) {
        console.warn('Failed to save tutorial state to localStorage:', e);
      }
    }
  }, []);

  const completeTutorial = useCallback(() => {
    setShowTutorial(false);
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem('skillsight-tutorial-completed', 'true');
      } catch (e) {
        console.warn('Failed to save tutorial state to localStorage:', e);
      }
    }
  }, []);

  return (
    <TutorialContext.Provider
      value={{
        showTutorial,
        currentStep,
        totalSteps,
        tutorialName,
        setTutorialName,
        startTutorial,
        nextStep,
        prevStep,
        skipTutorial,
        completeTutorial,
      }}
    >
      {children}
    </TutorialContext.Provider>
  );
}

const defaultTutorialContext: TutorialContextType = {
  showTutorial: false,
  currentStep: 0,
  totalSteps: 5,
  tutorialName: '',
  setTutorialName: () => {},
  startTutorial: () => {},
  nextStep: () => {},
  prevStep: () => {},
  skipTutorial: () => {},
  completeTutorial: () => {},
};

export function useTutorial() {
  const context = useContext(TutorialContext);
  return context ?? defaultTutorialContext;
}

export { getDateLocale } from './getDateLocale';
