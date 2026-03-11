'use client';

import { createContext, useCallback, useContext, useState } from 'react';

export type AssessmentWidgetType =
  | 'communication'
  | 'programming'
  | 'writing'
  | 'data_analysis'
  | 'problem_solving'
  | 'presentation';

export interface AssessmentWidgetContextValue {
  assessmentType: AssessmentWidgetType | null;
  skillId: string | null;
  skillName: string | null;
  setContext: (ctx: {
    assessmentType: AssessmentWidgetType;
    skillId: string;
    skillName: string;
  } | null) => void;
  isOpen: boolean;
  openWidget: () => void;
  closeWidget: () => void;
  onAssessmentComplete?: (assessment: {
    level: number;
    evidence_chunk_ids: string[];
    why?: string;
  }) => void;
  setOnAssessmentComplete: (
    cb: ((assessment: { level: number; evidence_chunk_ids: string[]; why?: string }) => void) | undefined
  ) => void;
}

const AssessmentWidgetContext = createContext<AssessmentWidgetContextValue | null>(null);

export function AssessmentWidgetProvider({ children }: { children: React.ReactNode }) {
  const [assessmentType, setAssessmentType] = useState<AssessmentWidgetType | null>(null);
  const [skillId, setSkillId] = useState<string | null>(null);
  const [skillName, setSkillName] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [onAssessmentComplete, setOnAssessmentCompleteState] = useState<
    ((assessment: { level: number; evidence_chunk_ids: string[]; why?: string }) => void) | undefined
  >(undefined);

  const setContext = useCallback(
    (ctx: { assessmentType: AssessmentWidgetType; skillId: string; skillName: string } | null) => {
      if (!ctx) {
        setAssessmentType(null);
        setSkillId(null);
        setSkillName(null);
        return;
      }
      setAssessmentType(ctx.assessmentType);
      setSkillId(ctx.skillId);
      setSkillName(ctx.skillName);
    },
    []
  );

  const openWidget = useCallback(() => setIsOpen(true), []);
  const closeWidget = useCallback(() => setIsOpen(false), []);

  const setOnAssessmentComplete = useCallback(
    (cb: ((assessment: { level: number; evidence_chunk_ids: string[]; why?: string }) => void) | undefined) => {
      setOnAssessmentCompleteState(cb);
    },
    []
  );

  const value: AssessmentWidgetContextValue = {
    assessmentType,
    skillId,
    skillName,
    setContext,
    isOpen,
    openWidget,
    closeWidget,
    onAssessmentComplete: onAssessmentComplete ?? undefined,
    setOnAssessmentComplete,
  };

  return (
    <AssessmentWidgetContext.Provider value={value}>
      {children}
    </AssessmentWidgetContext.Provider>
  );
}

export function useAssessmentWidget() {
  const ctx = useContext(AssessmentWidgetContext);
  return ctx;
}
