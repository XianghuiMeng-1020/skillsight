/**
 * Intermediate structured resume (aligned with backend `resume_structured.ResumeJsonDocument`).
 * Used for typed integrations and future editor/JSON export.
 */
export interface ResumeJsonBasics {
  name?: string;
  label?: string;
  email?: string;
  phone?: string;
  url?: string;
  summary?: string;
}

export type ResumeSectionKind =
  | 'summary'
  | 'experience'
  | 'education'
  | 'skills'
  | 'projects'
  | 'other';

export interface ResumeJsonSection {
  title: string;
  lines: string[];
  /** Present when produced by backend structured layer */
  kind?: ResumeSectionKind;
}

export interface ResumeJsonDocument {
  basics?: ResumeJsonBasics;
  sections?: ResumeJsonSection[];
  locale_hint?: 'en' | 'zh' | 'mixed' | 'auto';
}
