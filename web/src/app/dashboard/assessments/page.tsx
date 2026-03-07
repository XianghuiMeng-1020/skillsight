'use client';

import { useEffect, useRef, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { getToken, studentBff } from '@/lib/bffClient';

type AssessmentType =
  | 'communication'
  | 'programming'
  | 'writing'
  | 'data_analysis'
  | 'problem_solving'
  | 'presentation';

interface Session {
  session_id: string;
  topic?: string;
  problem?: { title: string; description: string; function_signature?: string };
  prompt?: { title: string; prompt: string };
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
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('easy');

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
    { id: 'data_analysis' as const, titleKey: 'assess.dataAnalysis', icon: '📊', descKey: 'assessmentsList.dataAnalysisDesc', timeKey: 'assessmentsList.time20_35', featuresKeys: ['assessmentsList.datasetInterpretation', 'assessmentsList.visualizationRecommendation', 'assessmentsList.aiInsightScoring'], color: 'teal', comingSoon: true },
    { id: 'problem_solving' as const, titleKey: 'assess.problemSolving', icon: '🧩', descKey: 'assessmentsList.problemSolvingDesc', timeKey: 'assessmentsList.time20_30', featuresKeys: ['assessmentsList.caseAnalysis', 'assessmentsList.structuredThinking', 'assessmentsList.multiStepReasoning'], color: 'orange', comingSoon: true },
    { id: 'presentation' as const, titleKey: 'assess.presentation', icon: '🎤', descKey: 'assessmentsList.presentationDesc', timeKey: 'assessmentsList.time8_10', featuresKeys: ['assessmentsList.structuredPresentation', 'assessmentsList.persuasionScoring', 'assessmentsList.visualAidRecommendation'], color: 'pink', comingSoon: true },
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

  const formatAssessmentType = (type: string) => {
    if (type === 'communication') return t('assessmentsList.typeCommunication');
    if (type === 'programming') return t('assessmentsList.typeProgramming');
    if (type === 'writing') return t('assessmentsList.typeWriting');
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
        case 'communication':
          endpoint = '/interactive/communication/submit';
          body = {
            session_id: session.session_id,
            transcript: 'This is a simulated transcript of my response to the topic. I believe effective communication is essential for success in any professional environment.',
            audio_duration_seconds: 45,
          };
          break;
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
      if (data?.idempotent_replay) {
        setUiHint(t('assessmentsList.idempotentReplayHint'));
      } else if (data?.skill_update?.queued) {
        setUiHint(t('assessmentsList.skillSyncQueuedHint'));
      } else {
        setUiHint(null);
      }
      fetchRecentUpdates();
    } catch {
      addToast('error', t('assessmentsList.submissionFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const resetAssessment = () => {
    setSession(null);
    setResult(null);
    setCode('');
    setEssay('');
    setRecording(false);
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
                <div style={{ display: 'flex', gap: '2rem', marginTop: '0.75rem' }}>
                  <div>
                    <div style={{ fontSize: '2rem', fontWeight: 700 }}>
                      {getEvaluation().overall_score as number || getEvaluation().score as number || 'N/A'}
                    </div>
                    <div style={{ fontSize: '0.875rem', opacity: 0.8 }}>{t('common.score')}</div>
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
                    className="assessment-card"
                    style={{ 
                      cursor: 'pointer',
                      borderColor: activeTab === assessment.id ? 'var(--primary)' : undefined,
                      boxShadow: activeTab === assessment.id ? '0 0 0 2px var(--primary-50)' : undefined
                    }}
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
                      {assessment.comingSoon ? (
                        <span className="badge badge-secondary">{t('assessmentsList.comingSoon')}</span>
                      ) : activeTab === assessment.id ? (
                        <span className="badge badge-primary">{t('assessmentsList.selected')}</span>
                      ) : (
                        <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('assessmentsList.clickToSelect')}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Start Section */}
              <div className="card">
                <div className="card-header">
                  <h3 className="card-title">
                    {assessments.find(a => a.id === activeTab)?.icon}{' '}
                    {assessments.find(a => a.id === activeTab) && t(assessments.find(a => a.id === activeTab)!.titleKey)} {t('assess.assessmentSuffix')}
                  </h3>
                </div>
                <div className="card-content" style={{ textAlign: 'center', padding: '2rem' }}>
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
                  
                  <p style={{ color: 'var(--gray-600)', marginBottom: '1.5rem', maxWidth: '500px', margin: '0 auto 1.5rem' }}>
                    {activeTab === 'communication' && t('assessmentsList.descComm')}
                    {activeTab === 'programming' && t('assessmentsList.descProg')}
                    {activeTab === 'writing' && t('assessmentsList.descWriting')}
                  </p>
                  
                  <button 
                    className="btn btn-primary btn-lg"
                    onClick={startSession}
                    disabled={loading || !!assessments.find((a) => a.id === activeTab)?.comingSoon}
                  >
                    {loading ? (
                      <>
                        <span className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></span>
                        {t('assessmentsList.starting')}
                      </>
                    ) : t('assessmentsList.startAssessment')}
                  </button>
                  {assessments.find((a) => a.id === activeTab)?.comingSoon && (
                    <p style={{ marginTop: '0.75rem', color: 'var(--gray-500)' }}>
                      {t('assessmentsList.comingSoonHint')}
                    </p>
                  )}
                </div>
              </div>
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
                </h3>
                <button className="btn btn-ghost btn-sm" onClick={resetAssessment}>
                  {t('assessmentsList.cancel')}
                </button>
              </div>
              <div className="card-content">
                {/* Communication Session */}
                {activeTab === 'communication' && session.topic && (
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
                      <div style={{ 
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
                        {recording ? '🔴' : '🎙️'}
                      </div>
                      
                      <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>
                        {t('assess.timeLimit')}: {session.duration_seconds} s
                      </p>
                      
                      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                        <button 
                          className={`btn ${recording ? 'btn-danger' : 'btn-primary'}`}
                          onClick={() => setRecording(!recording)}
                        >
                          {recording ? t('assessmentsList.stopRecording') : t('assessmentsList.startRecording')}
                        </button>
                        
                        {!recording && (
                          <button 
                            className="btn btn-secondary"
                            onClick={submitAssessment}
                            disabled={submitting}
                          >
                            {submitting ? t('assessmentsList.submitting') : t('assessmentsList.submitResponse')}
                          </button>
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
                      className="input"
                      style={{ 
                        fontFamily: 'monospace',
                        minHeight: '250px',
                        resize: 'vertical',
                        fontSize: '0.875rem'
                      }}
                      placeholder="def solution(...):\n    # Write your code here"
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
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
