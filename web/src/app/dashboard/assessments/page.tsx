'use client';

import { useEffect, useRef, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { getToken, studentBff } from '@/lib/bffClient';
import { useAssessmentWidget } from '@/lib/AssessmentWidgetContext';
import { useAudioRecorder, useWhisperTranscriber, useAchievements } from '@/lib/hooks';

type AssessmentType =
  | 'communication'
  | 'programming'
  | 'writing'
  | 'data_analysis'
  | 'problem_solving'
  | 'presentation';

const ASSESSMENT_TYPE_TO_SKILL: Record<AssessmentType, string> = {
  communication: 'HKU.SKILL.COMMUNICATION.v1',
  programming: 'HKU.SKILL.PYTHON.v1',
  writing: 'HKU.SKILL.COMMUNICATION.v1',
  data_analysis: 'HKU.SKILL.DATA_ANALYSIS.v1',
  problem_solving: 'HKU.SKILL.CRITICAL_THINKING.v1',
  presentation: 'HKU.SKILL.COMMUNICATION.v1',
};

interface Session {
  session_id: string;
  topic?: string | { id: string; title: string; topic: string };
  problem?: { title: string; description: string; function_signature?: string };
  prompt?: { title: string; prompt: string };
  dataset?: {
    id: string;
    title: string;
    summary: string;
    columns: string[];
    rows: (string | number)[][];
    question: string;
  };
  case?: { id: string; title: string; description: string };
  time_limit_minutes?: number;
  duration_seconds?: number;
  anti_copy_token?: string;
}

interface RecentUpdateItem {
  session_id: string;
  assessment_type: string;
  skill_id: string;
  score: number;
  level: number;
  submitted_at?: string;
  skill_update?: {
    level?: number;
    label?: string;
    updated_at?: string;
  } | null;
}

export default function AssessmentsPage() {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [activeTab, setActiveTab] = useState<AssessmentType>('communication');
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [recentUpdates, setRecentUpdates] = useState<RecentUpdateItem[]>([]);
  const [uiHint, setUiHint] = useState<string | null>(null);
  const lastActionAtRef = useRef(0);
  const idempotencyKeyRef = useRef<string | null>(null);
  
  const [code, setCode] = useState('');
  const [essay, setEssay] = useState('');
  const [dataAnalysis, setDataAnalysis] = useState('');
  const [dataVisualization, setDataVisualization] = useState('');
  const [caseResponse, setCaseResponse] = useState('');
  const [presentationOutline, setPresentationOutline] = useState('');
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('easy');
  const [agentAssessmentResult, setAgentAssessmentResult] = useState<{ level: number; why?: string } | null>(null);
  const assessmentWidget = useAssessmentWidget();
  const [transcriptResult, setTranscriptResult] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);

  const audioRecorder = useAudioRecorder();
  const whisperTranscriber = useWhisperTranscriber();
  const { checkAssessmentAchievements } = useAchievements();

  const getCurrentUserId = () => {
    if (typeof window === 'undefined') return 'demo_user';
    try {
      const raw = localStorage.getItem('user');
      if (!raw) return 'demo_user';
      const user = JSON.parse(raw) as { id?: string; subject_id?: string };
      return user.id || user.subject_id || 'demo_user';
    } catch {
      return 'demo_user';
    }
  };

  const assessments = [
    { id: 'communication' as const, titleKey: 'assess.communication', icon: '🎙️', descKey: 'assessmentsList.videoResponse', timeKey: 'assessmentsList.time1_2', featuresKeys: ['assessmentsList.randomTopic', 'assessmentsList.speakFreely', 'assessmentsList.upTo3Retries', 'assessmentsList.aiEval'], color: 'purple' },
    { id: 'programming' as const, titleKey: 'assess.programming', icon: '💻', descKey: 'assessmentsList.algorithmChallenges', timeKey: 'assessmentsList.time15_30', featuresKeys: ['assessmentsList.difficultyLevels', 'assessmentsList.realWorldProblems', 'assessmentsList.codeAnalysis', 'assessmentsList.instantFeedback'], color: 'blue' },
    { id: 'writing' as const, titleKey: 'assess.writing', icon: '✍️', descKey: 'assessmentsList.timedEssay', timeKey: 'assessmentsList.time30', featuresKeys: ['assessmentsList.words300_500', 'assessmentsList.antiCopy', 'assess.grammar', 'assessmentsList.styleFeedback'], color: 'green' },
    { id: 'data_analysis' as const, titleKey: 'assess.dataAnalysis', icon: '📊', descKey: 'assessmentsList.dataAnalysisDesc', timeKey: 'assessmentsList.time20_35', featuresKeys: ['assessmentsList.datasetInterpretation', 'assessmentsList.visualizationRecommendation', 'assessmentsList.aiInsightScoring'], color: 'teal' },
    { id: 'problem_solving' as const, titleKey: 'assess.problemSolving', icon: '🧩', descKey: 'assessmentsList.problemSolvingDesc', timeKey: 'assessmentsList.time20_30', featuresKeys: ['assessmentsList.caseAnalysis', 'assessmentsList.structuredThinking', 'assessmentsList.multiStepReasoning'], color: 'orange' },
    { id: 'presentation' as const, titleKey: 'assess.presentation', icon: '🎤', descKey: 'assessmentsList.presentationDesc', timeKey: 'assessmentsList.time8_10', featuresKeys: ['assessmentsList.structuredPresentation', 'assessmentsList.persuasionScoring', 'assessmentsList.visualAidRecommendation'], color: 'pink' },
  ];

  const fetchRecentUpdates = async () => {
    if (!getToken()) return;
    try {
      const data = await studentBff.getRecentAssessmentUpdates(6);
      setRecentUpdates((data.items || []) as RecentUpdateItem[]);
    } catch {
      setRecentUpdates([]);
    }
  };

  useEffect(() => {
    fetchRecentUpdates();
  }, []);

  useEffect(() => {
    if (!assessmentWidget) return;
    assessmentWidget.setOnAssessmentComplete((assessment) => {
      setAgentAssessmentResult({ level: assessment?.level ?? 0, why: assessment?.why });
      fetchRecentUpdates();
    });
    return () => assessmentWidget.setOnAssessmentComplete(undefined);
  }, [assessmentWidget]);

  const formatAssessmentType = (type: string) => {
    if (type === 'communication') return t('assessmentsList.typeCommunication');
    if (type === 'programming') return t('assessmentsList.typeProgramming');
    if (type === 'writing') return t('assessmentsList.typeWriting');
    if (type === 'data_analysis') return t('assess.dataAnalysis');
    if (type === 'problem_solving') return t('assess.problemSolving');
    if (type === 'presentation') return t('assess.presentation');
    return type;
  };

  const startSession = async () => {
    if (Date.now() - lastActionAtRef.current < 800) {
      setUiHint(t('assessmentsList.actionDebounced'));
      return;
    }
    lastActionAtRef.current = Date.now();
    setLoading(true);
    setResult(null);
    setUiHint(null);
    
    try {
      let endpoint = '';
      let body = {};
      const userId = getCurrentUserId();
      
      switch (activeTab) {
        case 'communication':
          endpoint = '/interactive/communication/start';
          body = { user_id: userId, duration_seconds: 60, allow_retries: true };
          break;
        case 'programming':
          endpoint = '/interactive/programming/start';
          body = { user_id: userId, difficulty, language: 'python' };
          break;
        case 'writing':
          endpoint = '/interactive/writing/start';
          body = { user_id: userId, time_limit_minutes: 30, min_words: 300, max_words: 500 };
          break;
        case 'data_analysis':
          endpoint = '/interactive/data_analysis/start';
          body = { user_id: userId };
          break;
        case 'problem_solving':
          endpoint = '/interactive/problem_solving/start';
          body = { user_id: userId };
          break;
        case 'presentation':
          endpoint = '/interactive/presentation/start';
          body = { user_id: userId };
          break;
        default:
          throw new Error('Coming soon');
      }
      
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
        body: JSON.stringify(body),
      });
      
      if (!response.ok) throw new Error('Failed to start');
      
      const data = await response.json();
      setSession(data);
      idempotencyKeyRef.current = null;
    } catch {
      addToast('error', t('assessmentsList.couldNotStart'));
    } finally {
      setLoading(false);
    }
  };

  const submitAssessment = async () => {
    if (!session) return;
    if (Date.now() - lastActionAtRef.current < 800) {
      setUiHint(t('assessmentsList.actionDebounced'));
      return;
    }
    lastActionAtRef.current = Date.now();
    setSubmitting(true);
    
    try {
      let endpoint = '';
      let body = {};
      const payloadSeed = `${session.session_id}:${activeTab}:${Date.now()}`;
      if (!idempotencyKeyRef.current) {
        idempotencyKeyRef.current = payloadSeed;
      }
      
      switch (activeTab) {
        case 'communication': {
          let transcript = '';
          if (transcriptResult !== null) {
            transcript = transcriptResult;
          } else if (audioRecorder.audioBlob) {
            const transcriptionResult = await whisperTranscriber.transcribeAudio(audioRecorder.audioBlob);
            transcript = transcriptionResult?.text ?? t('assess.transcribeFailed');
          } else {
            transcript = t('assess.noAudio');
          }
          endpoint = '/interactive/communication/submit';
          body = {
            session_id: session.session_id,
            transcript,
            audio_duration_seconds: audioRecorder.duration || 0,
          };
          break;
        }
        case 'programming':
          endpoint = '/interactive/programming/submit';
          body = { session_id: session.session_id, code, language: 'python' };
          break;
        case 'writing':
          endpoint = '/interactive/writing/submit';
          body = {
            session_id: session.session_id,
            content: essay,
            anti_copy_token: session.anti_copy_token || 'demo_token',
            keystroke_data: { chars_per_minute: 180, paste_count: 0 },
          };
          break;
        case 'data_analysis':
          endpoint = '/interactive/data_analysis/submit';
          body = {
            session_id: session.session_id,
            analysis: dataAnalysis,
            visualization: dataVisualization,
          };
          break;
        case 'problem_solving':
          endpoint = '/interactive/problem_solving/submit';
          body = { session_id: session.session_id, response: caseResponse };
          break;
        case 'presentation': {
          let transcript = transcriptResult ?? '';
          if (!transcript && audioRecorder.audioBlob) {
            const res = await whisperTranscriber.transcribeAudio(audioRecorder.audioBlob);
            transcript = res?.text ?? t('assess.transcribeFailed');
          }
          endpoint = '/interactive/presentation/submit';
          body = {
            session_id: session.session_id,
            transcript,
            outline: presentationOutline,
            audio_duration_seconds: audioRecorder.duration || 0,
          };
          break;
        }
        default:
          throw new Error('Coming soon');
      }
      
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
          'Idempotency-Key': idempotencyKeyRef.current,
          'X-Model-Version': 'ui-default-v1',
          'X-Rubric-Version': 'rubric-v1',
        },
        body: JSON.stringify(body),
      });
      
      if (!response.ok) throw new Error('Submit failed');
      
      const data = await response.json();
      setResult(data);
      setSession(null);
      idempotencyKeyRef.current = null;
      const score = typeof data?.score === 'number' ? data.score : (data?.evaluation as { score?: number })?.score ?? 0;
      if (['communication', 'programming', 'writing', 'data_analysis', 'problem_solving', 'presentation'].includes(activeTab)) {
        checkAssessmentAchievements(activeTab, score);
      }
      if (data?.idempotent_replay) {
        setUiHint(t('assessmentsList.idempotentReplayHint'));
      } else if (data?.skill_update?.queued) {
        setUiHint(t('assessmentsList.skillSyncQueuedHint'));
      } else {
        setUiHint(null);
      }
      fetchRecentUpdates();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      addToast('error', msg && msg.length < 120 ? msg : (t('assessmentsList.submissionFailed') || 'Assessment service temporarily unavailable. Please try again.'));
    } finally {
      setSubmitting(false);
    }
  };

  const resetAssessment = () => {
    setSession(null);
    setResult(null);
    setCode('');
    setEssay('');
    setDataAnalysis('');
    setDataVisualization('');
    setCaseResponse('');
    setPresentationOutline('');
    setRecording(false);
    setTranscriptResult(null);
    setTranscribing(false);
  };

  const getEvaluation = () => {
    const eval_ = result?.evaluation as Record<string, unknown> | undefined;
    return eval_ || {};
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('assessmentsList.pageTitle')}</h1>
            <p className="page-subtitle">{t('assessmentsList.pageSubtitle')}</p>
          </div>
        </div>

        <div className="page-content">
          {/* Result Display */}
          {result && (
            <div className="alert alert-success fade-in" style={{ marginBottom: '1.5rem' }}>
              <span className="alert-icon">✓</span>
              <div className="alert-content" style={{ flex: 1 }}>
                <div className="alert-title">{t('assessmentsList.complete')}</div>
                {Boolean((result?.skill_update as Record<string, unknown> | undefined)?.updated) && (
                  <div style={{ marginTop: '0.375rem', fontSize: '0.875rem', color: 'var(--success)' }}>
                    ✅ {t('assessmentsList.updatedSkillNow')}
                  </div>
                )}
                {Boolean((result?.skill_update as Record<string, unknown> | undefined)?.queued) && (
                  <div style={{ marginTop: '0.375rem', fontSize: '0.875rem', color: 'var(--warning, #a16207)' }}>
                    ⏳ {t('assessmentsList.skillSyncQueuedHint')}
                  </div>
                )}
                {uiHint && (
                  <div style={{ marginTop: '0.375rem', fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                    {uiHint}
                  </div>
                )}
                <div style={{ display: 'flex', gap: '2rem', marginTop: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div 
                    className="score-circle score-circle-animated" 
                    style={{ ['--score' as string]: (getEvaluation().overall_score as number) ?? (getEvaluation().score as number) ?? 0 }}
                  >
                    <div className="score-circle-inner">
                      <div className="score-value">{Math.round((getEvaluation().overall_score as number) || (getEvaluation().score as number) || 0)}</div>
                      <div className="score-label">{t('common.score')}</div>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '2rem', fontWeight: 700 }}>
                      {getEvaluation().level_label as string || getEvaluation().level as string || 'N/A'}
                    </div>
                    <div style={{ fontSize: '0.875rem', opacity: 0.8 }}>{t('common.level')}</div>
                  </div>
                </div>
                <button 
                  className="btn btn-secondary btn-sm" 
                  style={{ marginTop: '1rem' }}
                  onClick={resetAssessment}
                >
                  {t('assessmentsList.tryAnother')}
                </button>
              </div>
            </div>
          )}

          {/* Assessment Selection */}
          {!session && !result && (
            <>
              <div className="card" style={{ marginBottom: '1rem' }}>
                <div className="card-header">
                  <h3 className="card-title">{t('assessmentsList.recentUpdatesTitle')}</h3>
                </div>
                <div className="card-content">
                  <p style={{ color: 'var(--gray-600)', marginBottom: '0.75rem' }}>{t('assessmentsList.recentUpdatesHint')}</p>
                  {recentUpdates.length === 0 ? (
                    <div style={{ color: 'var(--gray-500)', fontSize: '0.875rem' }}>{t('assessmentsList.noRecentUpdates')}</div>
                  ) : (
                    <div style={{ display: 'grid', gap: '0.5rem' }}>
                      {recentUpdates.slice(0, 4).map((item) => (
                        <div
                          key={item.session_id}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            padding: '0.625rem 0.75rem',
                            background: 'var(--gray-50)',
                            borderRadius: 'var(--radius)',
                          }}
                        >
                          <div style={{ fontSize: '0.875rem', color: 'var(--gray-700)' }}>
                            <strong>{formatAssessmentType(item.assessment_type)}</strong> · {item.skill_id}
                          </div>
                          <div style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
                            {t('common.score')}: {Math.round(item.score || 0)}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="card" style={{ marginBottom: '1.5rem' }}>
                <div className="card-header">
                  <h3 className="card-title">{t('assessmentsList.skillCoverageTitle')}</h3>
                </div>
                <div className="card-content">
                  <p style={{ color: 'var(--gray-600)', marginBottom: '0.75rem' }}>{t('assessmentsList.skillCoverageSubtitle')}</p>
                  <div style={{ display: 'grid', gap: '0.5rem' }}>
                    <div style={{ padding: '0.625rem 0.75rem', borderRadius: 'var(--radius)', background: 'var(--gray-50)' }}>
                      <strong>{t('assessmentsList.coverageCommunication')}</strong>: {t('assessmentsList.coverageCommunicationDesc')}
                    </div>
                    <div style={{ padding: '0.625rem 0.75rem', borderRadius: 'var(--radius)', background: 'var(--gray-50)' }}>
                      <strong>{t('assessmentsList.coverageCoding')}</strong>: {t('assessmentsList.coverageCodingDesc')}
                    </div>
                    <div style={{ padding: '0.625rem 0.75rem', borderRadius: 'var(--radius)', background: 'var(--gray-50)' }}>
                      <strong>{t('assessmentsList.coverageWriting')}</strong>: {t('assessmentsList.coverageWritingDesc')}
                    </div>
                  </div>
                </div>
              </div>

              <h2 style={{ marginBottom: '1rem' }}>{t('assessmentsList.chooseType')}</h2>
              <div className="assessment-grid" style={{ marginBottom: '2rem' }}>
                {assessments.map((assessment) => (
                  <div 
                    key={assessment.id}
                    className={`assessment-card ${activeTab === assessment.id ? 'selected' : ''}`}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setActiveTab(assessment.id)}
                  >
                    <div className="assessment-header">
                      <div className="assessment-icon">{assessment.icon}</div>
                      <div className="assessment-title">{t(assessment.titleKey)}</div>
                      <div className="assessment-subtitle">{t(assessment.descKey)}</div>
                    </div>
                    <div className="assessment-content">
                      <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginBottom: '0.75rem' }}>
                        ⏱️ {t(assessment.timeKey)}
                      </div>
                      <ul className="assessment-features">
                        {assessment.featuresKeys.map((fk, i) => (
                          <li key={i}>{t(fk)}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="assessment-footer">
                      {activeTab === assessment.id ? (
                        <span className="badge badge-primary">{t('assessmentsList.selected')}</span>
                      ) : (
                        <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('assessmentsList.clickToSelect')}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Start Section: Traditional vs AI Agent */}
              <div className="card">
                <div className="card-header">
                  <h3 className="card-title">
                    {assessments.find(a => a.id === activeTab)?.icon}{' '}
                    {assessments.find(a => a.id === activeTab) && t(assessments.find(a => a.id === activeTab)!.titleKey)} {t('assess.assessmentSuffix')}
                  </h3>
                </div>
                <div className="card-content" style={{ padding: '2rem' }}>
                  {activeTab === 'programming' && (
                    <div style={{ marginBottom: '1.5rem' }}>
                      <div style={{ fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.75rem' }}>
                        {t('assessmentsList.selectDifficulty')}
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                        {(['easy', 'medium', 'hard'] as const).map((d) => (
                          <button
                            key={d}
                            className={`btn ${difficulty === d ? 'btn-primary' : 'btn-secondary'} btn-sm`}
                            onClick={() => setDifficulty(d)}
                          >
                            {d === 'easy' ? `🟢 ${t('assess.easy')}` : d === 'medium' ? `🟡 ${t('assess.medium')}` : `🔴 ${t('assess.hard')}`}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <p style={{ color: 'var(--gray-600)', marginBottom: '1.5rem', maxWidth: '500px', margin: '0 auto 1.5rem', textAlign: 'center' }}>
                    {activeTab === 'communication' && t('assessmentsList.descComm')}
                    {activeTab === 'programming' && t('assessmentsList.descProg')}
                    {activeTab === 'writing' && t('assessmentsList.descWriting')}
                    {(activeTab === 'data_analysis' || activeTab === 'problem_solving' || activeTab === 'presentation') && t('assessmentsList.comingSoonHint')}
                  </p>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '400px', margin: '0 auto' }}>
                    <button
                      className="btn btn-secondary"
                      onClick={startSession}
                      disabled={loading}
                    >
                      {loading ? (
                        <>
                          <span className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px', marginRight: '0.5rem' }} />
                          {t('assessmentsList.starting')}
                        </>
                      ) : (
                        t('assess.traditionalMode')
                      )}
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        setAgentAssessmentResult(null);
                        assessmentWidget?.setContext({
                          assessmentType: activeTab,
                          skillId: ASSESSMENT_TYPE_TO_SKILL[activeTab],
                          skillName: assessments.find((a) => a.id === activeTab)
                            ? (t(assessments.find((a) => a.id === activeTab)!.titleKey) as string)
                            : activeTab.replace(/_/g, ' '),
                        });
                        assessmentWidget?.openWidget();
                      }}
                    >
                      🤖 {t('assess.aiAgentMode')}
                    </button>
                  </div>
                  
                </div>
              </div>

              {agentAssessmentResult !== null && (
                <div className="alert alert-success" style={{ marginTop: '1.5rem' }}>
                  <span className="alert-icon">✓</span>
                  <div className="alert-content">
                    <div className="alert-title">{t('assessmentsList.complete')}</div>
                    <p style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>
                      Level: {agentAssessmentResult.level} (0=novice, 1=developing, 2=proficient, 3=advanced).
                      {agentAssessmentResult.why && ` ${agentAssessmentResult.why}`}
                    </p>
                    <button className="btn btn-secondary btn-sm" style={{ marginTop: '0.5rem' }} onClick={() => setAgentAssessmentResult(null)}>
                      {t('common.close')}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Active Session */}
          {session && (
            <div className="card fade-in">
              <div className="card-header">
                <h3 className="card-title">
                  {activeTab === 'communication' && `🎙️ ${t('assess.communicationAssess')}`}
                  {activeTab === 'programming' && `💻 ${t('assess.programming')} ${t('assessmentsList.challenge')}`}
                  {activeTab === 'writing' && `✍️ ${t('assess.writing')} ${t('assess.assessmentSuffix')}`}
                  {activeTab === 'data_analysis' && `📊 ${t('assess.dataAnalysis')} ${t('assess.assessmentSuffix')}`}
                  {activeTab === 'problem_solving' && `🧩 ${t('assess.problemSolving')} ${t('assess.assessmentSuffix')}`}
                  {activeTab === 'presentation' && `🎤 ${t('assess.presentation')} ${t('assess.assessmentSuffix')}`}
                </h3>
                <button className="btn btn-ghost btn-sm" onClick={resetAssessment}>
                  {t('assessmentsList.cancel')}
                </button>
              </div>
              <div className="card-content">
                {/* Communication Session */}
                {activeTab === 'communication' && session.topic && typeof session.topic === 'string' && (
                  <>
                    <div style={{ 
                      background: 'var(--primary-50)', 
                      padding: '1.5rem', 
                      borderRadius: 'var(--radius-lg)',
                      marginBottom: '1.5rem'
                    }}>
                      <div style={{ fontSize: '0.875rem', color: 'var(--primary)', marginBottom: '0.5rem', fontWeight: 500 }}>
                        {t('assessmentsList.yourTopic')}
                      </div>
                      <div style={{ fontSize: '1.125rem', fontWeight: 500 }}>{session.topic}</div>
                    </div>
                    
                    <div style={{ textAlign: 'center' }}>
                      <div className={recording ? 'recording-indicator' : ''} style={{ 
                        width: '120px', 
                        height: '120px', 
                        borderRadius: '50%',
                        background: recording ? 'var(--error-light)' : 'var(--gray-100)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '3rem',
                        margin: '0 auto 1rem',
                        transition: 'all 0.3s ease'
                      }}>
                        {recording ? (
                          <div className="recording-waves" style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                            {[1, 2, 3, 4, 5].map((i) => (
                              <span key={i} className="recording-wave" style={{ width: '6px', borderRadius: '3px', background: 'var(--error)' }} />
                            ))}
                          </div>
                        ) : '🎙️'}
                      </div>
                      
                      <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>
                        {t('assess.timeLimit')}: {session.duration_seconds} s
                      </p>
                      
                      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                        <button 
                          className={`btn ${recording ? 'btn-danger' : 'btn-primary'}`}
                          onClick={async () => {
                            if (recording) {
                              const blob = await audioRecorder.stopRecording();
                              setRecording(false);
                              setTranscriptResult(null);
                              if (blob) {
                                setTranscribing(true);
                                try {
                                  const res = await whisperTranscriber.transcribeAudio(blob);
                                  setTranscriptResult(res?.text ?? t('assess.transcribeFailed'));
                                } catch {
                                  setTranscriptResult(t('assess.transcribeFailed'));
                                } finally {
                                  setTranscribing(false);
                                }
                              }
                            } else {
                              await audioRecorder.startRecording();
                              setRecording(true);
                            }
                          }}
                        >
                          {recording ? t('assessmentsList.stopRecording') : t('assessmentsList.startRecording')}
                        </button>
                        
                        {!recording && (
                          <button 
                            className="btn btn-secondary"
                            onClick={submitAssessment}
                            disabled={submitting || transcribing}
                          >
                            {transcribing ? t('assessmentsList.transcribing') : submitting ? t('assessmentsList.submitting') : t('assessmentsList.submitResponse')}
                          </button>
                        )}
                        {transcriptResult !== null && !transcriptResult.startsWith(t('assess.transcribeFailed')) && !transcriptResult.startsWith(t('assess.noAudio')) && (
                          <p style={{ fontSize: '0.8125rem', color: 'var(--gray-500)', marginTop: '0.5rem', maxWidth: '360px', marginLeft: 'auto', marginRight: 'auto' }}>
                            {t('assessmentsList.transcriptReady')}
                          </p>
                        )}
                      </div>
                    </div>
                  </>
                )}

                {/* Programming Session */}
                {activeTab === 'programming' && session.problem && (
                  <>
                    <div style={{ 
                      background: 'var(--gray-50)', 
                      padding: '1.5rem', 
                      borderRadius: 'var(--radius-lg)',
                      marginBottom: '1.5rem'
                    }}>
                      <h4 style={{ marginBottom: '0.75rem' }}>{session.problem.title}</h4>
                      <p style={{ 
                        color: 'var(--gray-600)', 
                        fontSize: '0.875rem',
                        whiteSpace: 'pre-wrap',
                        marginBottom: '1rem'
                      }}>
                        {session.problem.description}
                      </p>
                      {session.problem.function_signature && (
                        <code style={{ 
                          display: 'block', 
                          background: 'var(--gray-800)', 
                          color: 'var(--gray-100)',
                          padding: '0.75rem',
                          borderRadius: 'var(--radius)',
                          fontSize: '0.875rem'
                        }}>
                          {session.problem.function_signature}
                        </code>
                      )}
                    </div>
                    
                    <label className="label">{t('assessmentsList.yourSolution')}</label>
                    <textarea
                      className="input code-editor-dark"
                      style={{ fontSize: '0.875rem' }}
                      placeholder="def solution(...):&#10;    # Write your code here"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                    />
                    
                    <button 
                      className="btn btn-primary"
                      style={{ marginTop: '1rem', width: '100%' }}
                      onClick={submitAssessment}
                      disabled={!code.trim() || submitting}
                    >
                      {submitting ? t('assessmentsList.evaluating') : t('assessmentsList.submitSolution')}
                    </button>
                  </>
                )}

                {/* Writing Session */}
                {activeTab === 'writing' && session.prompt && (
                  <>
                    <div style={{ 
                      background: 'var(--hku-green-50)', 
                      padding: '1.5rem', 
                      borderRadius: 'var(--radius-lg)',
                      marginBottom: '1.5rem'
                    }}>
                      <div style={{ fontSize: '0.875rem', color: 'var(--hku-green)', marginBottom: '0.5rem', fontWeight: 500 }}>
                        ✏️ {session.prompt.title}
                      </div>
                      <div style={{ fontSize: '1rem' }}>
                        {session.prompt.prompt}
                      </div>
                      <div style={{ 
                        fontSize: '0.75rem', 
                        color: 'var(--gray-500)',
                        marginTop: '0.75rem'
                      }}>
                        ⏱️ Time limit: {session.time_limit_minutes} minutes · Word count: 300-500 words
                      </div>
                    </div>
                    
                    <div style={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      marginBottom: '0.5rem'
                    }}>
                      <label className="label" style={{ margin: 0 }}>{t('assessmentsList.yourEssay')}</label>
                      <span style={{ 
                        fontSize: '0.875rem', 
                        color: essay.split(/\s+/).filter(Boolean).length >= 300 ? 'var(--success)' : 'var(--gray-500)' 
                      }}>
                        {essay.split(/\s+/).filter(Boolean).length} words
                      </span>
                    </div>
                    
                    <textarea
                      className="input"
                      style={{ 
                        minHeight: '300px',
                        resize: 'vertical',
                        lineHeight: '1.8'
                      }}
                      placeholder="Start typing your essay here..."
                      value={essay}
                      onChange={(e) => setEssay(e.target.value)}
                    />
                    
                    <button 
                      className="btn btn-primary"
                      style={{ marginTop: '1rem', width: '100%' }}
                      onClick={submitAssessment}
                      disabled={essay.split(/\s+/).filter(Boolean).length < 50 || submitting}
                    >
                      {submitting ? t('assessmentsList.evaluating') : t('assessmentsList.submitEssay')}
                    </button>
                  </>
                )}

                {/* Data Analysis Session */}
                {activeTab === 'data_analysis' && session.dataset && (
                  <>
                    <div style={{ background: 'var(--gray-50)', padding: '1rem', borderRadius: 'var(--radius-lg)', marginBottom: '1rem' }}>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>📊 {session.dataset.title}</div>
                      <p style={{ fontSize: '0.8125rem', color: 'var(--gray-600)', marginBottom: '0.75rem' }}>{session.dataset.summary}</p>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                          <thead>
                            <tr>
                              {session.dataset.columns.map((col, i) => (
                                <th key={i} style={{ border: '1px solid var(--gray-200)', padding: '0.5rem', textAlign: 'left', background: 'var(--gray-100)' }}>{col}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {session.dataset.rows.map((row, ri) => (
                              <tr key={ri}>
                                {row.map((cell, ci) => (
                                  <td key={ci} style={{ border: '1px solid var(--gray-200)', padding: '0.5rem' }}>{String(cell)}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div style={{ marginTop: '1rem', fontSize: '0.875rem', fontWeight: 500, color: 'var(--gray-700)' }}>
                        {session.dataset.question}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '0.5rem' }}>
                        ⏱️ {session.time_limit_minutes} min
                      </div>
                    </div>
                    <label className="label">{t('assessmentsList.yourEssay')}</label>
                    <textarea
                      className="input"
                      style={{ minHeight: '180px', resize: 'vertical', marginBottom: '0.75rem' }}
                      placeholder="Your analysis and insights..."
                      value={dataAnalysis}
                      onChange={(e) => setDataAnalysis(e.target.value)}
                    />
                    <label className="label" style={{ marginBottom: '0.25rem' }}>Visualization recommendation</label>
                    <select
                      className="input"
                      style={{ marginBottom: '1rem' }}
                      value={dataVisualization}
                      onChange={(e) => setDataVisualization(e.target.value)}
                    >
                      <option value="">— Select —</option>
                      <option value="bar">Bar chart</option>
                      <option value="line">Line chart</option>
                      <option value="scatter">Scatter plot</option>
                      <option value="pie">Pie chart</option>
                      <option value="table">Table</option>
                    </select>
                    <button
                      className="btn btn-primary"
                      style={{ width: '100%' }}
                      onClick={submitAssessment}
                      disabled={!dataAnalysis.trim() || submitting}
                    >
                      {submitting ? t('assessmentsList.evaluating') : t('assessmentsList.submitResponse')}
                    </button>
                  </>
                )}

                {/* Problem Solving Session */}
                {activeTab === 'problem_solving' && session.case && (
                  <>
                    <div style={{ background: 'var(--gray-50)', padding: '1.5rem', borderRadius: 'var(--radius-lg)', marginBottom: '1rem' }}>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>🧩 {session.case.title}</div>
                      <p style={{ fontSize: '0.9375rem', color: 'var(--gray-700)', whiteSpace: 'pre-wrap' }}>{session.case.description}</p>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '0.5rem' }}>⏱️ {session.time_limit_minutes} min</div>
                    </div>
                    <label className="label">Your analysis (problem definition → analysis → solution → evaluation)</label>
                    <textarea
                      className="input"
                      style={{ minHeight: '280px', resize: 'vertical' }}
                      placeholder="1. Problem definition&#10;2. Analysis&#10;3. Solution&#10;4. Evaluation"
                      value={caseResponse}
                      onChange={(e) => setCaseResponse(e.target.value)}
                    />
                    <button
                      className="btn btn-primary"
                      style={{ marginTop: '1rem', width: '100%' }}
                      onClick={submitAssessment}
                      disabled={!caseResponse.trim() || submitting}
                    >
                      {submitting ? t('assessmentsList.evaluating') : t('assessmentsList.submitResponse')}
                    </button>
                  </>
                )}

                {/* Presentation Session */}
                {activeTab === 'presentation' && session.topic && typeof session.topic === 'object' && (
                  <>
                    <div style={{ background: 'var(--primary-50)', padding: '1.5rem', borderRadius: 'var(--radius-lg)', marginBottom: '1rem' }}>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>🎤 {session.topic.title}</div>
                      <p style={{ fontSize: '0.9375rem', color: 'var(--gray-700)' }}>{session.topic.topic}</p>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '0.5rem' }}>⏱️ {session.time_limit_minutes} min</div>
                    </div>
                    <label className="label">Outline (intro, main points, conclusion)</label>
                    <textarea
                      className="input"
                      style={{ minHeight: '100px', resize: 'vertical', marginBottom: '1rem' }}
                      placeholder="1. Introduction&#10;2. Main point 1&#10;3. Main point 2&#10;4. Conclusion"
                      value={presentationOutline}
                      onChange={(e) => setPresentationOutline(e.target.value)}
                    />
                    <div style={{ textAlign: 'center', marginBottom: '1rem' }}>
                      <div style={{ width: '100px', height: '100px', borderRadius: '50%', background: recording ? 'var(--error-light)' : 'var(--gray-100)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2.5rem', margin: '0 auto 0.75rem' }}>
                        {recording ? '🔴' : '🎤'}
                      </div>
                      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                        <button
                          className={`btn ${recording ? 'btn-danger' : 'btn-primary'}`}
                          onClick={async () => {
                            if (recording) {
                              const blob = await audioRecorder.stopRecording();
                              setRecording(false);
                              setTranscriptResult(null);
                              if (blob) {
                                setTranscribing(true);
                                try {
                                  const res = await whisperTranscriber.transcribeAudio(blob);
                                  setTranscriptResult(res?.text ?? t('assess.transcribeFailed'));
                                } catch {
                                  setTranscriptResult(t('assess.transcribeFailed'));
                                } finally {
                                  setTranscribing(false);
                                }
                              }
                            } else {
                              await audioRecorder.startRecording();
                              setRecording(true);
                            }
                          }}
                        >
                          {recording ? t('assessmentsList.stopRecording') : t('assessmentsList.startRecording')}
                        </button>
                        {!recording && (
                          <button
                            className="btn btn-secondary"
                            onClick={submitAssessment}
                            disabled={submitting || transcribing}
                          >
                            {transcribing ? t('assessmentsList.transcribing') : submitting ? t('assessmentsList.submitting') : t('assessmentsList.submitResponse')}
                          </button>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
