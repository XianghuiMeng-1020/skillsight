'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useAudioRecorder, useWhisperTranscriber, useCodeExecutor, useAIWritingFeedback, useAchievements } from '@/lib/hooks';
import { AchievementNotification } from '@/components/Achievements';
import { useLanguage } from '@/lib/contexts';
import { API_BASE_URL } from '@/lib/api';
import { getToken } from '@/lib/bffClient';

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
  problem?: { title: string; description: string };
  prompt?: string;
  duration_seconds?: number;
  time_limit_minutes?: number;
  anti_copy_token?: string;
}

interface EvaluationResult {
  overall_score?: number;
  score?: number;
  level?: string;
  clarity?: number;
  content?: number;
  confidence?: number;
  grammar?: number;
  structure?: number;
  creativity?: number;
  correctness?: number;
  efficiency?: number;
  style?: number;
  feedback?: string;
}

// SkillSight Logo Component
const SkillSightLogo = ({ size = 28 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path 
      d="M16 6C8 6 2 16 2 16C2 16 8 26 16 26C24 26 30 16 30 16C30 16 24 6 16 6Z" 
      fill="url(#eyeGradientAssess)" 
      stroke="white" 
      strokeWidth="1.5"
    />
    <circle cx="16" cy="16" r="6" fill="white" opacity="0.9"/>
    <path 
      d="M12 19L14.5 16L16.5 17.5L20 13" 
      stroke="#E18182" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    />
    <circle cx="13" cy="13" r="1.5" fill="white" opacity="0.8"/>
    <circle cx="20" cy="13" r="1.5" fill="#E18182"/>
    <defs>
      <linearGradient id="eyeGradientAssess" x1="2" y1="16" x2="30" y2="16" gradientUnits="userSpaceOnUse">
        <stop stopColor="#F9CE9C"/>
        <stop offset="0.5" stopColor="#E18182"/>
        <stop offset="1" stopColor="#C9DDE3"/>
      </linearGradient>
    </defs>
  </svg>
);

// Circular Score Component
const ScoreCircle = ({ score, label, color = '#E18182' }: { score: number; label: string; color?: string }) => {
  const [animatedScore, setAnimatedScore] = useState(0);
  
  useEffect(() => {
    const timer = setTimeout(() => setAnimatedScore(score), 100);
    return () => clearTimeout(timer);
  }, [score]);

  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{
        width: '100px',
        height: '100px',
        borderRadius: '50%',
        background: `conic-gradient(${color} ${animatedScore * 3.6}deg, #E7E5E4 0deg)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        margin: '0 auto',
        boxShadow: `0 8px 24px -8px ${color}40`,
        transition: 'all 0.8s cubic-bezier(0.4, 0, 0.2, 1)'
      }}>
        <div style={{
          width: '80px',
          height: '80px',
          borderRadius: '50%',
          background: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column'
        }}>
          <span style={{ fontSize: '1.75rem', fontWeight: 700, color: '#1C1917' }}>{score}</span>
        </div>
      </div>
      <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#78716C', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
    </div>
  );
};

// Score Bar Component
const ScoreBar = ({ label, score, icon, color }: { label: string; score: number; icon: string; color: string }) => (
  <div style={{ marginBottom: '0.75rem' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
      <span style={{ fontSize: '0.875rem', color: '#44403C', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <span>{icon}</span> {label}
      </span>
      <span style={{ fontSize: '0.875rem', fontWeight: 600, color }}>{score}/100</span>
    </div>
    <div style={{ height: '8px', background: '#E7E5E4', borderRadius: '9999px', overflow: 'hidden' }}>
      <div style={{
        width: `${score}%`,
        height: '100%',
        background: `linear-gradient(90deg, ${color}80, ${color})`,
        borderRadius: '9999px',
        transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)'
      }} />
    </div>
  </div>
);

// Level Badge Component (label is translated by parent)
const LevelBadge = ({ level, label }: { level: string; label: string }) => {
  const levelConfig: Record<string, { bg: string; text: string; icon: string }> = {
    beginner: { bg: 'linear-gradient(135deg, #E4EEF1, #C9DDE3)', text: '#57534E', icon: '🌱' },
    intermediate: { bg: 'linear-gradient(135deg, #FBE0BC, #F9CE9C)', text: '#44403C', icon: '🌿' },
    advanced: { bg: 'linear-gradient(135deg, #D6E5DD, #98B8A8)', text: '#292524', icon: '🌳' },
    expert: { bg: 'linear-gradient(135deg, #F0A5A6, #E18182)', text: 'white', icon: '⭐' },
  };
  const config = levelConfig[level.toLowerCase()] || levelConfig.beginner;
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.5rem',
      padding: '0.5rem 1rem',
      borderRadius: '9999px',
      background: config.bg,
      color: config.text,
      fontWeight: 600,
      fontSize: '0.875rem',
      boxShadow: '0 2px 8px -2px rgba(0,0,0,0.1)'
    }}>
      <span>{config.icon}</span>
      {label}
    </span>
  );
};

export default function AssessPage() {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<AssessmentType>('communication');
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [timer, setTimer] = useState(0);
  const [uiHint, setUiHint] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const lastActionAtRef = useRef(0);
  const idempotencyKeyRef = useRef<string | null>(null);
  
  // Form states
  const [code, setCode] = useState('');
  const [essay, setEssay] = useState('');
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('easy');
  const [codeOutput, setCodeOutput] = useState<string | null>(null);
  
  // 音频录制和转录
  const audioRecorder = useAudioRecorder();
  const whisperTranscriber = useWhisperTranscriber();
  
  // 代码执行
  const codeExecutor = useCodeExecutor();
  
  // AI 写作反馈
  const { feedback: aiFeedback, isAnalyzing: isAnalyzingWriting, analyzeWriting } = useAIWritingFeedback();
  
  // 成就系统
  const { recentUnlock, checkAssessmentAchievements, dismissRecentUnlock } = useAchievements();

  // Timer effect
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (audioRecorder.isRecording || (session && activeTab === 'writing')) {
      interval = setInterval(() => {
        setTimer(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [audioRecorder.isRecording, session, activeTab]);
  
  // AI 写作分析 - 当文本变化时分析
  useEffect(() => {
    if (activeTab === 'writing' && essay.length > 50) {
      analyzeWriting(essay, session?.prompt);
    }
  }, [essay, activeTab, session?.prompt, analyzeWriting]);

  const formatTime = useCallback((seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }, []);

  const tabs = [
    { id: 'communication' as const, labelKey: 'assess.communication', icon: '🎙️', descKey: 'assess.videoStyle', color: '#E18182' },
    { id: 'programming' as const, labelKey: 'assess.programming', icon: '💻', descKey: 'assess.leetcodeStyle', color: '#98B8A8' },
    { id: 'writing' as const, labelKey: 'assess.writing', icon: '✍️', descKey: 'assess.timedWriting', color: '#F9CE9C' },
    { id: 'data_analysis' as const, labelKey: 'assess.dataAnalysis', icon: '📊', descKey: 'assessmentsList.dataAnalysisDesc', color: '#9FC5CF', comingSoon: true },
    { id: 'problem_solving' as const, labelKey: 'assess.problemSolving', icon: '🧩', descKey: 'assessmentsList.problemSolvingDesc', color: '#F0A36B', comingSoon: true },
    { id: 'presentation' as const, labelKey: 'assess.presentation', icon: '🎤', descKey: 'assessmentsList.presentationDesc', color: '#D793B6', comingSoon: true },
  ];

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

  const startSession = async () => {
    if (Date.now() - lastActionAtRef.current < 800) {
      setUiHint(t('assessmentsList.actionDebounced'));
      return;
    }
    lastActionAtRef.current = Date.now();
    setLoading(true);
    setResult(null);
    setUiHint(null);
    setStartError(null);
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
          throw new Error(t('assessmentsList.comingSoonHint'));
      }
      
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
        body: JSON.stringify(body),
      });
      
      if (!response.ok) throw new Error(t('assess.startFailed'));
      
      const data = await response.json();
      setSession(data);
      idempotencyKeyRef.current = null;
    } catch {
      const msg = t('assess.startFailedMsg') as string;
      setStartError(msg);
      alert(msg);
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
      let transcript = '';
      const payloadSeed = `${session.session_id}:${activeTab}:${Date.now()}`;
      if (!idempotencyKeyRef.current) {
        idempotencyKeyRef.current = payloadSeed;
      }
      
      switch (activeTab) {
        case 'communication':
          // 如果有录音，先转录
          if (audioRecorder.audioBlob) {
            const transcriptionResult = await whisperTranscriber.transcribeAudio(audioRecorder.audioBlob);
            transcript = transcriptionResult?.text || t('assess.transcribeFailed');
          } else {
            transcript = t('assess.noAudio');
          }
          
          endpoint = '/interactive/communication/submit';
          body = {
            session_id: session.session_id,
            transcript,
            audio_duration_seconds: audioRecorder.duration,
          };
          break;
        case 'programming':
          endpoint = '/interactive/programming/submit';
          body = {
            session_id: session.session_id,
            code,
            language: 'python',
          };
          break;
        case 'writing':
          endpoint = '/interactive/writing/submit';
          body = {
            session_id: session.session_id,
            content: essay,
            anti_copy_token: session.anti_copy_token ?? '',
            keystroke_data: { chars_per_minute: 180, paste_count: 0 },
          };
          break;
        default:
          throw new Error(t('assessmentsList.comingSoonHint'));
      }
      
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
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
      
      if (!response.ok) throw new Error(t('assess.submitFailed'));
      
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
      
      const evalResult = data.evaluation as EvaluationResult;
      const score = evalResult?.overall_score || evalResult?.score || 0;
      checkAssessmentAchievements(activeTab, score);
      
    } catch {
      alert(t('assess.submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };
  
  // 运行代码测试
  const runCodeTests = async () => {
    if (!code.trim()) return;
    
    const result = await codeExecutor.executeCode(code, 'python');
    setCodeOutput(result.output || result.error || t('assess.noOutput'));
  };

  const resetAssessment = () => {
    setSession(null);
    setResult(null);
    setCode('');
    setEssay('');
    setTimer(0);
    setCodeOutput(null);
    audioRecorder.resetRecording();
    whisperTranscriber.reset();
  };

  // Get evaluation data
  const evaluation = result?.evaluation as EvaluationResult | undefined;
  const overallScore = evaluation?.overall_score || evaluation?.score || 0;
  const level = evaluation?.level || 'Beginner';
  const levelLabel = (() => {
    const k = level.toLowerCase();
    if (k === 'beginner') return t('assess.levelBeginner');
    if (k === 'intermediate') return t('assess.levelIntermediate');
    if (k === 'advanced') return t('assess.levelAdvanced');
    if (k === 'expert') return t('assess.levelExpert');
    return level;
  })();

  return (
    <div className="page">
      {/* Header */}
      <header className="header" style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(10px)' }}>
        <div className="header-inner">
          <Link href="/" className="logo" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <div style={{
              background: 'linear-gradient(135deg, #F9CE9C, #E18182)',
              borderRadius: '10px',
              padding: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 12px -2px rgba(225, 129, 130, 0.3)'
            }}>
              <SkillSightLogo size={24} />
            </div>
            <span style={{ fontWeight: 700, color: '#1C1917' }}>SkillSight</span>
          </Link>
          <nav className="nav">
            <Link href="/" className="nav-link">{t('nav.home')}</Link>
            <Link href="/upload" className="nav-link">{t('nav.upload')}</Link>
            <Link href="/assess" className="nav-link active">{t('nav.assess')}</Link>
            <Link href="/dashboard" className="nav-link">{t('nav.dashboard')}</Link>
          </nav>
        </div>
      </header>

      <main className="main" style={{ background: 'linear-gradient(180deg, rgba(249,206,156,0.05) 0%, rgba(201,221,227,0.05) 100%)' }}>
        <div className="container" style={{ maxWidth: '900px' }}>
          {/* Page Title */}
          <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
            <h1 style={{ 
              marginBottom: '0.75rem', 
              fontSize: '2rem',
              background: 'linear-gradient(135deg, #1C1917, #44403C)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}>
              {t('assess.title')}
            </h1>
            <p style={{ color: '#78716C', fontSize: '1rem' }}>
              {t('assess.subtitle')}
            </p>
          </div>

          {/* Result Display - Enhanced */}
          {result && (
            <div className="card fade-in" style={{ 
              marginBottom: '2rem',
              background: 'linear-gradient(135deg, rgba(255,255,255,0.98), rgba(249,206,156,0.05))',
              border: '1px solid rgba(249,206,156,0.3)',
              boxShadow: '0 12px 40px -12px rgba(225,129,130,0.2)'
            }}>
              <div className="card-header" style={{ 
                background: 'linear-gradient(90deg, rgba(249,206,156,0.1), rgba(225,129,130,0.1))',
                borderBottom: '1px solid rgba(249,206,156,0.2)'
              }}>
                <h3 style={{ fontSize: '1.125rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #98B8A8, #BBCFC3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.875rem'
                  }}>✓</span>
                  {t('assess.result')}
                </h3>
                <button className="btn btn-ghost btn-sm" onClick={resetAssessment} style={{ color: '#E18182' }}>
                  🔄 {t('assess.retry')}
                </button>
              </div>
              <div className="card-content" style={{ padding: '2rem' }}>
                {uiHint && (
                  <div style={{ marginBottom: '1rem', fontSize: '0.875rem', color: '#57534E' }}>
                    {uiHint}
                  </div>
                )}
                {/* Main Score Section */}
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: '1fr 2fr',
                  gap: '2rem',
                  marginBottom: '2rem'
                }}>
                  {/* Overall Score Circle */}
                  <div style={{ textAlign: 'center' }}>
                    <ScoreCircle score={overallScore} label={t('assess.totalScore')} color="#E18182" />
                    <div style={{ marginTop: '1rem' }}>
                      <LevelBadge level={level} label={levelLabel} />
                    </div>
                  </div>
                  
                  {/* Score Breakdown */}
                  <div>
                    {activeTab === 'communication' && (
                      <>
                        <ScoreBar label={t('assess.clarity')} score={evaluation?.clarity || 75} icon="🗣️" color="#E18182" />
                        <ScoreBar label={t('assess.content')} score={evaluation?.content || 80} icon="📝" color="#F9CE9C" />
                        <ScoreBar label={t('assess.confidence')} score={evaluation?.confidence || 70} icon="💪" color="#98B8A8" />
                      </>
                    )}
                    {activeTab === 'programming' && (
                      <>
                        <ScoreBar label={t('assess.correctness')} score={evaluation?.correctness || 85} icon="✅" color="#98B8A8" />
                        <ScoreBar label={t('assess.efficiency')} score={evaluation?.efficiency || 75} icon="⚡" color="#F9CE9C" />
                        <ScoreBar label={t('assess.codeStyle')} score={evaluation?.style || 80} icon="✨" color="#E18182" />
                      </>
                    )}
                    {activeTab === 'writing' && (
                      <>
                        <ScoreBar label={t('assess.grammar')} score={evaluation?.grammar || 85} icon="📖" color="#98B8A8" />
                        <ScoreBar label={t('assess.structure')} score={evaluation?.structure || 78} icon="🏗️" color="#F9CE9C" />
                        <ScoreBar label={t('assess.creativity')} score={evaluation?.creativity || 82} icon="💡" color="#E18182" />
                      </>
                    )}
                  </div>
                </div>

                {/* Feedback Section */}
                {evaluation?.feedback && (
                  <div style={{
                    background: 'linear-gradient(135deg, rgba(249,206,156,0.1), rgba(201,221,227,0.1))',
                    borderRadius: '12px',
                    padding: '1.25rem',
                    marginBottom: '1.5rem'
                  }}>
                    <h4 style={{ 
                      fontSize: '0.875rem', 
                      color: '#44403C', 
                      marginBottom: '0.5rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem'
                    }}>
                      <span>💬</span> {t('assess.aiFeedback')}
                    </h4>
                    <p style={{ fontSize: '0.875rem', color: '#57534E', lineHeight: 1.6 }}>
                      {evaluation.feedback}
                    </p>
                  </div>
                )}

                {/* Detailed Data Toggle */}
                <details style={{ fontSize: '0.875rem', color: '#78716C' }}>
                  <summary style={{ 
                    cursor: 'pointer', 
                    marginBottom: '0.5rem',
                    padding: '0.5rem',
                    borderRadius: '8px',
                    transition: 'background 0.2s'
                  }}>
                    📊 {t('assess.detailedData')}
                  </summary>
                  <pre style={{ 
                    background: '#FAFAF9', 
                    padding: '1rem', 
                    borderRadius: '12px',
                    overflow: 'auto',
                    fontSize: '0.75rem',
                    border: '1px solid #E7E5E4'
                  }}>
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </details>
              </div>
            </div>
          )}

          {/* Tab Navigation - Enhanced */}
          <div style={{ 
            display: 'flex', 
            gap: '1rem', 
            marginBottom: '2rem',
            flexWrap: 'wrap',
          }}>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); resetAssessment(); }}
                style={{
                  flex: 1,
                  padding: '1.25rem 1rem',
                  border: activeTab === tab.id ? `2px solid ${tab.color}` : '2px solid #E7E5E4',
                  borderRadius: '16px',
                  background: activeTab === tab.id 
                    ? `linear-gradient(135deg, ${tab.color}10, white)` 
                    : 'white',
                  boxShadow: activeTab === tab.id 
                    ? `0 8px 24px -8px ${tab.color}40` 
                    : '0 2px 8px -2px rgba(0,0,0,0.05)',
                  cursor: 'pointer',
                  transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                  transform: activeTab === tab.id ? 'translateY(-2px)' : 'translateY(0)',
                }}
              >
                <div style={{ 
                  fontSize: '2rem', 
                  marginBottom: '0.5rem',
                  filter: activeTab === tab.id ? 'none' : 'grayscale(0.5)'
                }}>
                  {tab.icon}
                </div>
                <div style={{ 
                  fontWeight: 600, 
                  color: activeTab === tab.id ? '#1C1917' : '#78716C',
                  fontSize: '0.9375rem'
                }}>
                  {t(tab.labelKey)}
                </div>
                <div style={{ 
                  fontSize: '0.75rem', 
                  color: '#A8A29E',
                  marginTop: '0.25rem'
                }}>
                  {t(tab.descKey)}
                </div>
                {tab.comingSoon && (
                  <div style={{ marginTop: '0.375rem' }}>
                    <span style={{
                      display: 'inline-block',
                      fontSize: '0.6875rem',
                      padding: '0.125rem 0.5rem',
                      borderRadius: '9999px',
                      background: '#F5F5F4',
                      color: '#78716C',
                      border: '1px solid #E7E5E4',
                    }}>
                      {t('assessmentsList.comingSoon')}
                    </span>
                  </div>
                )}
              </button>
            ))}
          </div>

          {/* Assessment Content */}
          <div className="card" style={{ 
            border: '1px solid #E7E5E4',
            boxShadow: '0 4px 20px -8px rgba(0,0,0,0.08)',
            overflow: 'hidden'
          }}>
            <div className="card-content" style={{ padding: '2rem' }}>
              {!session && !result && (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  {activeTab === 'communication' && (
                    <>
                      <div style={{ 
                        fontSize: '4rem', 
                        marginBottom: '1rem',
                        width: '100px',
                        height: '100px',
                        borderRadius: '50%',
                        background: 'linear-gradient(135deg, rgba(225,129,130,0.1), rgba(225,129,130,0.2))',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        margin: '0 auto 1.5rem'
                      }}>🎙️</div>
                      <h3 style={{ marginBottom: '0.75rem', fontSize: '1.25rem', color: '#1C1917' }}>{t('assess.communicationAssess')}</h3>
                      <p style={{ color: '#78716C', marginBottom: '1.5rem', maxWidth: '400px', margin: '0 auto 1.5rem', lineHeight: 1.6 }}>
                        {t('assess.commIntro')}
                      </p>
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'center', 
                        gap: '2rem', 
                        marginBottom: '1.5rem',
                        color: '#57534E',
                        fontSize: '0.875rem'
                      }}>
                        <span>⏱️ {t('assess.recording60')}</span>
                        <span>🔄 {t('assess.retry3')}</span>
                        <span>🤖 {t('assess.aiScore')}</span>
                      </div>
                    </>
                  )}
                  
                  {activeTab === 'programming' && (
                    <>
                      <div style={{ 
                        fontSize: '4rem', 
                        marginBottom: '1rem',
                        width: '100px',
                        height: '100px',
                        borderRadius: '50%',
                        background: 'linear-gradient(135deg, rgba(152,184,168,0.1), rgba(152,184,168,0.2))',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        margin: '0 auto 1.5rem'
                      }}>💻</div>
                      <h3 style={{ marginBottom: '0.75rem', fontSize: '1.25rem', color: '#1C1917' }}>{t('assess.programmingTitle')}</h3>
                      <p style={{ color: '#78716C', marginBottom: '1.25rem', maxWidth: '400px', margin: '0 auto 1.25rem' }}>
                        {t('assess.programmingDesc')}
                      </p>
                      <div style={{ 
                        display: 'flex', 
                        gap: '0.75rem', 
                        justifyContent: 'center',
                        marginBottom: '1.5rem'
                      }}>
                        {(['easy', 'medium', 'hard'] as const).map((d) => {
                          const config = {
                            easy: { label: `🌱 ${t('assess.easy')}`, color: '#98B8A8' },
                            medium: { label: `🌿 ${t('assess.medium')}`, color: '#F9CE9C' },
                            hard: { label: `🔥 ${t('assess.hard')}`, color: '#E18182' }
                          };
                          return (
                            <button
                              key={d}
                              onClick={() => setDifficulty(d)}
                              style={{
                                padding: '0.75rem 1.5rem',
                                border: difficulty === d ? `2px solid ${config[d].color}` : '2px solid #E7E5E4',
                                borderRadius: '12px',
                                background: difficulty === d 
                                  ? `linear-gradient(135deg, ${config[d].color}20, white)` 
                                  : 'white',
                                cursor: 'pointer',
                                fontWeight: 500,
                                fontSize: '0.875rem',
                                color: difficulty === d ? '#1C1917' : '#78716C',
                                transition: 'all 0.2s ease',
                                boxShadow: difficulty === d ? `0 4px 12px -4px ${config[d].color}60` : 'none'
                              }}
                            >
                              {config[d].label}
                            </button>
                          );
                        })}
                      </div>
                    </>
                  )}
                  
                  {activeTab === 'writing' && (
                    <>
                      <div style={{ 
                        fontSize: '4rem', 
                        marginBottom: '1rem',
                        width: '100px',
                        height: '100px',
                        borderRadius: '50%',
                        background: 'linear-gradient(135deg, rgba(249,206,156,0.1), rgba(249,206,156,0.2))',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        margin: '0 auto 1.5rem'
                      }}>✍️</div>
                      <h3 style={{ marginBottom: '0.75rem', fontSize: '1.25rem', color: '#1C1917' }}>{t('assess.writingTitle')}</h3>
                      <p style={{ color: '#78716C', marginBottom: '1.5rem', maxWidth: '400px', margin: '0 auto 1.5rem', lineHeight: 1.6 }}>
                        {t('assess.writingInstructions')}
                      </p>
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'center', 
                        gap: '2rem', 
                        marginBottom: '1.5rem',
                        color: '#57534E',
                        fontSize: '0.875rem'
                      }}>
                        <span>⏱️ 30 {t('assess.minutes')}</span>
                        <span>📝 300-500 {t('assess.words')}</span>
                        <span>🛡️ {t('assess.antiPlagiarism')}</span>
                      </div>
                    </>
                  )}
                  
                  <button 
                    onClick={startSession}
                    disabled={loading || !!tabs.find((item) => item.id === activeTab)?.comingSoon}
                    style={{
                      padding: '1rem 2.5rem',
                      fontSize: '1rem',
                      fontWeight: 600,
                      border: 'none',
                      borderRadius: '12px',
                      background: 'linear-gradient(135deg, #E18182, #C96A6B)',
                      color: 'white',
                      cursor: loading ? 'wait' : 'pointer',
                      boxShadow: '0 8px 24px -8px rgba(225,129,130,0.5)',
                      transition: 'all 0.3s ease',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      opacity: loading ? 0.7 : 1
                    }}
                  >
                    {loading ? (
                      <>
                        <div className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></div>
                        {t('assess.preparing')}
                      </>
                    ) : (
                      <>
                        ▶️ {t('assess.start')}
                      </>
                    )}
                  </button>
                  {startError && (
                    <p role="alert" style={{ color: 'var(--error, #b91c1c)', marginTop: '0.75rem', fontSize: '0.9rem' }}>
                      {startError}
                    </p>
                  )}
                  {tabs.find((item) => item.id === activeTab)?.comingSoon && (
                    <p style={{ color: '#78716C', marginTop: '0.75rem' }}>
                      {t('assessmentsList.comingSoonHint')}
                    </p>
                  )}
                </div>
              )}

              {session && (
                <div className="fade-in">
                  {/* Communication Session */}
                  {activeTab === 'communication' && session.topic && (
                    <>
                      <div style={{ 
                        background: 'linear-gradient(135deg, rgba(225,129,130,0.08), rgba(249,206,156,0.08))', 
                        padding: '1.5rem', 
                        borderRadius: '16px',
                        marginBottom: '2rem',
                        border: '1px solid rgba(225,129,130,0.2)'
                      }}>
                        <div style={{ 
                          fontSize: '0.75rem', 
                          color: '#E18182', 
                          marginBottom: '0.5rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.05em',
                          fontWeight: 600
                        }}>
                          📌 {t('assess.yourTopic')}
                        </div>
                        <div style={{ fontSize: '1.25rem', fontWeight: 600, color: '#1C1917' }}>
                          &ldquo;{session.topic}&rdquo;
                        </div>
                      </div>
                      
                      <div style={{ textAlign: 'center' }}>
                        {/* Recording Visualization */}
                        <div style={{ 
                          width: '140px', 
                          height: '140px', 
                          borderRadius: '50%',
                          background: audioRecorder.isRecording 
                            ? 'linear-gradient(135deg, rgba(225,129,130,0.2), rgba(225,129,130,0.1))' 
                            : 'linear-gradient(135deg, #F5F5F4, #E7E5E4)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          margin: '0 auto 1.5rem',
                          transition: 'all 0.3s ease',
                          boxShadow: audioRecorder.isRecording 
                            ? '0 0 0 8px rgba(225,129,130,0.1), 0 0 0 16px rgba(225,129,130,0.05)' 
                            : 'none',
                          animation: audioRecorder.isRecording ? 'pulse 2s infinite' : 'none'
                        }}>
                          {audioRecorder.isRecording ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', height: '40px' }}>
                              {[1,2,3,4,5].map((i) => (
                                <div key={i} style={{
                                  width: '6px',
                                  background: '#E18182',
                                  borderRadius: '3px',
                                  animation: `waveAnim 0.6s ease-in-out infinite`,
                                  animationDelay: `${i * 0.1}s`,
                                  height: `${20 + Math.floor(audioRecorder.audioLevel * 30) + (i % 3) * 10}px`
                                }} />
                              ))}
                            </div>
                          ) : (
                            <span style={{ fontSize: '3.5rem' }}>🎙️</span>
                          )}
                        </div>
                        
                        {/* Audio Level Indicator */}
                        {audioRecorder.isRecording && (
                          <div style={{
                            width: '200px',
                            height: '4px',
                            background: '#E7E5E4',
                            borderRadius: '9999px',
                            margin: '0 auto 1rem',
                            overflow: 'hidden',
                          }}>
                            <div style={{
                              width: `${audioRecorder.audioLevel * 100}%`,
                              height: '100%',
                              background: 'linear-gradient(90deg, #98B8A8, #E18182)',
                              borderRadius: '9999px',
                              transition: 'width 0.1s ease',
                            }} />
                          </div>
                        )}
                        
                        {/* Timer Display */}
                        <div style={{
                          fontSize: '2.5rem',
                          fontWeight: 700,
                          color: audioRecorder.isRecording 
                            ? (audioRecorder.duration > 50 ? '#E18182' : '#1C1917') 
                            : '#78716C',
                          marginBottom: '0.5rem',
                          fontFamily: 'Inter, monospace'
                        }}>
                          {formatTime(audioRecorder.isRecording ? audioRecorder.duration : (session.duration_seconds || 60))}
                        </div>
                        <p style={{ color: '#78716C', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
                          {audioRecorder.isRecording ? t('assess.recording') : 
                           whisperTranscriber.isTranscribing ? t('assess.transcribing') :
                           `${t('assess.timeLimit')}: ${session.duration_seconds} ${t('assess.seconds')}`}
                        </p>
                        
                        {/* 转录结果显示 */}
                        {whisperTranscriber.result && (
                          <div style={{
                            background: 'rgba(152,184,168,0.1)',
                            borderRadius: '12px',
                            padding: '1rem',
                            marginBottom: '1rem',
                            textAlign: 'left',
                          }}>
                            <div style={{ fontSize: '0.75rem', color: '#98B8A8', marginBottom: '0.5rem', fontWeight: 600 }}>
                              📝 {t('assess.transcriptionResult')}
                            </div>
                            <p style={{ fontSize: '0.875rem', color: '#44403C', lineHeight: 1.6 }}>
                              {whisperTranscriber.result.text}
                            </p>
                          </div>
                        )}
                        
                        {/* 录音播放 */}
                        {audioRecorder.audioUrl && !audioRecorder.isRecording && (
                          <div style={{ marginBottom: '1rem' }}>
                            <audio 
                              src={audioRecorder.audioUrl} 
                              controls 
                              style={{ width: '100%', maxWidth: '300px' }}
                            />
                          </div>
                        )}
                        
                        {/* 错误提示 */}
                        {(audioRecorder.error || whisperTranscriber.error) && (
                          <div style={{
                            background: 'rgba(225,129,130,0.1)',
                            borderRadius: '8px',
                            padding: '0.75rem',
                            marginBottom: '1rem',
                            color: '#E18182',
                            fontSize: '0.875rem',
                          }}>
                            ⚠️ {audioRecorder.error || whisperTranscriber.error}
                          </div>
                        )}
                        
                        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}>
                          <button 
                            onClick={async () => {
                              if (audioRecorder.isRecording) {
                                await audioRecorder.stopRecording();
                              } else {
                                await audioRecorder.startRecording();
                              }
                            }}
                            disabled={whisperTranscriber.isTranscribing}
                            style={{
                              padding: '0.875rem 1.75rem',
                              border: 'none',
                              borderRadius: '12px',
                              background: audioRecorder.isRecording 
                                ? 'linear-gradient(135deg, #E18182, #C96A6B)' 
                                : 'linear-gradient(135deg, #98B8A8, #7FA393)',
                              color: 'white',
                              fontWeight: 600,
                              cursor: whisperTranscriber.isTranscribing ? 'wait' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.5rem',
                              boxShadow: audioRecorder.isRecording
                                ? '0 4px 16px -4px rgba(225,129,130,0.5)'
                                : '0 4px 16px -4px rgba(152,184,168,0.5)',
                              transition: 'all 0.2s ease',
                              opacity: whisperTranscriber.isTranscribing ? 0.7 : 1,
                            }}
                          >
                            {audioRecorder.isRecording ? `⏹️ ${t('assess.stopRecording')}` : `▶️ ${t('assess.startRecording')}`}
                          </button>
                          
                          {!audioRecorder.isRecording && audioRecorder.audioBlob && (
                            <button 
                              onClick={submitAssessment}
                              disabled={submitting || whisperTranscriber.isTranscribing}
                              style={{
                                padding: '0.875rem 1.75rem',
                                border: '2px solid #E7E5E4',
                                borderRadius: '12px',
                                background: 'white',
                                color: '#44403C',
                                fontWeight: 600,
                                cursor: (submitting || whisperTranscriber.isTranscribing) ? 'wait' : 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                opacity: (submitting || whisperTranscriber.isTranscribing) ? 0.7 : 1,
                                transition: 'all 0.2s ease'
                              }}
                            >
                              {submitting ? t('assess.submitting') : whisperTranscriber.isTranscribing ? t('assess.transcribing') : `📤 ${t('assess.submitAssessment')}`}
                            </button>
                          )}
                        </div>
                      </div>
                    </>
                  )}

                  {/* Programming Session */}
                  {activeTab === 'programming' && session.problem && (
                    <>
                      {/* Problem Card */}
                      <div style={{ 
                        background: 'linear-gradient(135deg, #FAFAF9, #F5F5F4)', 
                        padding: '1.5rem', 
                        borderRadius: '16px',
                        marginBottom: '1.5rem',
                        border: '1px solid #E7E5E4'
                      }}>
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'space-between',
                          marginBottom: '1rem'
                        }}>
                          <h4 style={{ 
                            margin: 0, 
                            color: '#1C1917',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem'
                          }}>
                            <span style={{
                              width: '28px',
                              height: '28px',
                              borderRadius: '8px',
                              background: 'linear-gradient(135deg, #98B8A8, #BBCFC3)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.875rem'
                            }}>💡</span>
                            {session.problem.title}
                          </h4>
                          <span style={{
                            padding: '0.25rem 0.75rem',
                            borderRadius: '9999px',
                            background: difficulty === 'easy' 
                              ? 'linear-gradient(135deg, #D6E5DD, #BBCFC3)' 
                              : difficulty === 'medium'
                              ? 'linear-gradient(135deg, #FBE0BC, #F9CE9C)'
                              : 'linear-gradient(135deg, #F0A5A6, #E18182)',
                            color: difficulty === 'hard' ? 'white' : '#44403C',
                            fontSize: '0.75rem',
                            fontWeight: 600
                          }}>
                            {difficulty === 'easy' ? t('assess.easy') : difficulty === 'medium' ? t('assess.medium') : t('assess.hard')}
                          </span>
                        </div>
                        <p style={{ 
                          color: '#57534E', 
                          fontSize: '0.875rem',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.6
                        }}>
                          {session.problem.description}
                        </p>
                      </div>
                      
                      {/* Code Editor */}
                      <div style={{ marginBottom: '1rem' }}>
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'space-between',
                          marginBottom: '0.5rem'
                        }}>
                          <label style={{ fontWeight: 500, color: '#44403C', fontSize: '0.875rem' }}>
                            {t('assess.yourCode')} (Python)
                          </label>
                          <span style={{ fontSize: '0.75rem', color: '#A8A29E' }}>
                            {code.split('\n').length} {t('assess.lines')}
                          </span>
                        </div>
                        
                        {/* Code Editor Header */}
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                          padding: '0.75rem 1rem',
                          background: '#292524',
                          borderRadius: '12px 12px 0 0'
                        }}>
                          <span style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#ff5f56' }} />
                          <span style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#ffbd2e' }} />
                          <span style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#27ca40' }} />
                          <span style={{ marginLeft: '1rem', color: '#A8A29E', fontSize: '0.75rem' }}>solution.py</span>
                        </div>
                        
                        <textarea
                          style={{ 
                            width: '100%',
                            fontFamily: 'JetBrains Mono, Fira Code, monospace',
                            minHeight: '280px',
                            resize: 'vertical',
                            background: '#1C1917',
                            color: '#e2e8f0',
                            border: 'none',
                            borderRadius: '0 0 12px 12px',
                            padding: '1rem',
                            fontSize: '0.875rem',
                            lineHeight: 1.6,
                            outline: 'none'
                          }}
                          placeholder={`def solution(nums, target):\n    # ${t('assess.codePlaceholder')}\n    pass`}
                          value={code}
                          onChange={(e) => setCode(e.target.value)}
                        />
                      </div>
                      
                      {/* 代码运行输出 */}
                      {(codeOutput || codeExecutor.result) && (
                        <div style={{
                          marginBottom: '1rem',
                          background: '#1C1917',
                          borderRadius: '12px',
                          padding: '1rem',
                          fontFamily: 'JetBrains Mono, monospace',
                        }}>
                          <div style={{ 
                            display: 'flex', 
                            justifyContent: 'space-between', 
                            alignItems: 'center',
                            marginBottom: '0.5rem'
                          }}>
                            <span style={{ fontSize: '0.75rem', color: '#98B8A8', fontWeight: 600 }}>
                              📤 {t('assess.output')}
                            </span>
                            {codeExecutor.result?.executionTime && (
                              <span style={{ fontSize: '0.6875rem', color: '#A8A29E' }}>
                                ⏱️ {codeExecutor.result.executionTime.toFixed(2)}ms
                              </span>
                            )}
                          </div>
                          <pre style={{ 
                            color: codeExecutor.result?.error ? '#E18182' : '#e2e8f0',
                            fontSize: '0.8125rem',
                            whiteSpace: 'pre-wrap',
                            margin: 0,
                          }}>
                            {codeOutput || codeExecutor.result?.output || codeExecutor.result?.error}
                          </pre>
                          
                          {/* 测试结果 */}
                          {codeExecutor.result?.testResults && (
                            <div style={{ marginTop: '1rem', borderTop: '1px solid #44403C', paddingTop: '1rem' }}>
                              <div style={{ fontSize: '0.75rem', color: '#F9CE9C', marginBottom: '0.5rem', fontWeight: 600 }}>
                                🧪 {t('assess.testResults')}
                              </div>
                              {codeExecutor.result.testResults.map((test, i) => (
                                <div key={i} style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.5rem',
                                  padding: '0.375rem 0',
                                  fontSize: '0.8125rem',
                                }}>
                                  <span style={{ color: test.passed ? '#98B8A8' : '#E18182' }}>
                                    {test.passed ? '✓' : '✗'}
                                  </span>
                                  <span style={{ color: '#e2e8f0' }}>{test.name}</span>
                                  {!test.passed && (
                                    <span style={{ color: '#A8A29E', fontSize: '0.75rem' }}>
                                      ({t('assess.expected')}: {test.expected}, {t('assess.actual')}: {test.actual})
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      
                      {/* 按钮组 */}
                      <div style={{ display: 'flex', gap: '0.75rem' }}>
                        <button 
                          onClick={runCodeTests}
                          disabled={!code.trim() || codeExecutor.isExecuting}
                          style={{
                            flex: 1,
                            padding: '1rem',
                            border: '2px solid #E7E5E4',
                            borderRadius: '12px',
                            background: 'white',
                            color: !code.trim() || codeExecutor.isExecuting ? '#A8A29E' : '#44403C',
                            fontWeight: 600,
                            cursor: !code.trim() || codeExecutor.isExecuting ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '0.5rem',
                            transition: 'all 0.2s ease'
                          }}
                        >
                          {codeExecutor.isExecuting ? (
                            <>
                              <div className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></div>
                              {t('assess.running')}
                            </>
                          ) : (
                            <>▶️ {t('assess.runTests')}</>
                          )}
                        </button>
                        
                        <button 
                          onClick={submitAssessment}
                          disabled={!code.trim() || submitting}
                          style={{
                            flex: 1,
                            padding: '1rem',
                            border: 'none',
                            borderRadius: '12px',
                            background: !code.trim() || submitting 
                              ? '#E7E5E4' 
                              : 'linear-gradient(135deg, #98B8A8, #7FA393)',
                            color: !code.trim() || submitting ? '#A8A29E' : 'white',
                            fontWeight: 600,
                            cursor: !code.trim() || submitting ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '0.5rem',
                            boxShadow: code.trim() && !submitting 
                              ? '0 4px 16px -4px rgba(152,184,168,0.5)' 
                              : 'none',
                            transition: 'all 0.2s ease'
                          }}
                        >
                          {submitting ? (
                            <>
                              <div className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></div>
                              {t('assess.evaluating')}
                            </>
                          ) : (
                            <>🚀 {t('assess.submitCode')}</>
                          )}
                        </button>
                      </div>
                    </>
                  )}

                  {/* Writing Session */}
                  {activeTab === 'writing' && session.prompt && (
                    <>
                      {/* Writing Prompt Card */}
                      <div style={{ 
                        background: 'linear-gradient(135deg, rgba(249,206,156,0.08), rgba(201,221,227,0.08))', 
                        padding: '1.5rem', 
                        borderRadius: '16px',
                        marginBottom: '1.5rem',
                        border: '1px solid rgba(249,206,156,0.2)'
                      }}>
                        <div style={{ 
                          fontSize: '0.75rem', 
                          color: '#E8B87A', 
                          marginBottom: '0.5rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.05em',
                          fontWeight: 600
                        }}>
                          ✏️ {t('assess.writingPrompt')}
                        </div>
                        <div style={{ fontSize: '1.125rem', color: '#1C1917', fontWeight: 500 }}>
                          {session.prompt}
                        </div>
                        <div style={{ 
                          display: 'flex',
                          gap: '1.5rem',
                          marginTop: '1rem',
                          color: '#78716C',
                          fontSize: '0.875rem'
                        }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            ⏱️ {session.time_limit_minutes} {t('assess.minutes')}
                          </span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            📝 300-500 {t('assess.words')}
                          </span>
                        </div>
                      </div>
                      
                      {/* Timer and Word Count Bar */}
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        alignItems: 'center',
                        marginBottom: '0.75rem',
                        padding: '0.75rem 1rem',
                        background: 'linear-gradient(90deg, #FAFAF9, #F5F5F4)',
                        borderRadius: '12px',
                        border: '1px solid #E7E5E4'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{
                            padding: '0.25rem 0.75rem',
                            borderRadius: '9999px',
                            background: 'linear-gradient(135deg, #F9CE9C, #E8B87A)',
                            color: 'white',
                            fontSize: '0.875rem',
                            fontWeight: 600
                          }}>
                            ⏱️ {formatTime(timer)}
                          </span>
                          <span style={{ color: '#78716C', fontSize: '0.75rem' }}>
                            / {session.time_limit_minutes}:00
                          </span>
                        </div>
                        
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{ 
                            fontSize: '0.875rem', 
                            fontWeight: 600,
                            color: essay.length >= 300 ? '#98B8A8' : '#A8A29E'
                          }}>
                            {essay.length}
                          </span>
                          <span style={{ color: '#A8A29E', fontSize: '0.75rem' }}>/ 300-500 {t('assess.words')}</span>
                        </div>
                      </div>
                      
                      {/* Word Count Progress */}
                      <div style={{ 
                        height: '4px', 
                        background: '#E7E5E4', 
                        borderRadius: '9999px',
                        marginBottom: '1rem',
                        overflow: 'hidden'
                      }}>
                        <div style={{
                          width: `${Math.min((essay.length / 500) * 100, 100)}%`,
                          height: '100%',
                          background: essay.length >= 300 
                            ? 'linear-gradient(90deg, #98B8A8, #BBCFC3)' 
                            : 'linear-gradient(90deg, #F9CE9C, #E8B87A)',
                          borderRadius: '9999px',
                          transition: 'width 0.3s ease'
                        }} />
                      </div>
                      
                      {/* 编辑区和反馈区 */}
                      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1rem' }}>
                        {/* Essay Editor */}
                        <textarea
                          style={{ 
                            width: '100%',
                            minHeight: '320px',
                            resize: 'vertical',
                            lineHeight: '2',
                            padding: '1.25rem',
                            border: '2px solid #E7E5E4',
                            borderRadius: '16px',
                            fontSize: '1rem',
                            color: '#1C1917',
                            background: 'white',
                            outline: 'none',
                            transition: 'border-color 0.2s ease, box-shadow 0.2s ease'
                          }}
                          placeholder={t('assess.essayPlaceholder')}
                          value={essay}
                          onChange={(e) => setEssay(e.target.value)}
                          onFocus={(e) => {
                            e.currentTarget.style.borderColor = '#F9CE9C';
                            e.currentTarget.style.boxShadow = '0 0 0 4px rgba(249,206,156,0.1)';
                          }}
                          onBlur={(e) => {
                            e.currentTarget.style.borderColor = '#E7E5E4';
                            e.currentTarget.style.boxShadow = 'none';
                          }}
                        />
                        
                        {/* AI 实时反馈面板 */}
                        <div style={{
                          background: 'linear-gradient(180deg, #FAFAF9, #F5F5F4)',
                          borderRadius: '16px',
                          padding: '1rem',
                          border: '1px solid #E7E5E4',
                          overflowY: 'auto',
                          maxHeight: '320px',
                        }}>
                          <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'space-between',
                            marginBottom: '1rem'
                          }}>
                            <span style={{ 
                              fontSize: '0.75rem', 
                              color: '#78716C', 
                              fontWeight: 600,
                              textTransform: 'uppercase',
                              letterSpacing: '0.05em',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.375rem'
                            }}>
                              ✨ {t('assess.aiRealtimeFeedback')}
                            </span>
                            {isAnalyzingWriting && (
                              <div className="spinner" style={{ width: '14px', height: '14px', borderWidth: '2px' }}></div>
                            )}
                          </div>
                          
                          {aiFeedback ? (
                            <div style={{ fontSize: '0.8125rem' }}>
                              {/* 总分 */}
                              <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                marginBottom: '1rem',
                              }}>
                                <div style={{
                                  width: '60px',
                                  height: '60px',
                                  borderRadius: '50%',
                                  background: `conic-gradient(#98B8A8 ${aiFeedback.overall * 3.6}deg, #E7E5E4 0deg)`,
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                }}>
                                  <div style={{
                                    width: '50px',
                                    height: '50px',
                                    borderRadius: '50%',
                                    background: 'white',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontWeight: 700,
                                    color: '#1C1917',
                                  }}>
                                    {aiFeedback.overall}
                                  </div>
                                </div>
                              </div>
                              
                              {/* 分项评分 */}
                              {[
                                { label: t('assess.grammar'), score: aiFeedback.grammar.score, icon: '📖', color: '#98B8A8' },
                                { label: t('assess.content'), score: aiFeedback.content.score, icon: '📝', color: '#F9CE9C' },
                                { label: t('assess.structure'), score: aiFeedback.structure.score, icon: '🏗️', color: '#C9DDE3' },
                                { label: t('assess.style'), score: aiFeedback.style.score, icon: '✨', color: '#E18182' },
                              ].map(item => (
                                <div key={item.label} style={{ marginBottom: '0.75rem' }}>
                                  <div style={{ 
                                    display: 'flex', 
                                    justifyContent: 'space-between',
                                    marginBottom: '0.25rem'
                                  }}>
                                    <span style={{ color: '#57534E', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                      <span style={{ fontSize: '0.875rem' }}>{item.icon}</span>
                                      {item.label}
                                    </span>
                                    <span style={{ fontWeight: 600, color: item.color }}>{item.score}</span>
                                  </div>
                                  <div style={{
                                    height: '4px',
                                    background: '#E7E5E4',
                                    borderRadius: '9999px',
                                    overflow: 'hidden',
                                  }}>
                                    <div style={{
                                      width: `${item.score}%`,
                                      height: '100%',
                                      background: item.color,
                                      borderRadius: '9999px',
                                      transition: 'width 0.5s ease',
                                    }} />
                                  </div>
                                </div>
                              ))}
                              
                              {/* 建议 */}
                              {aiFeedback.content.suggestions.length > 0 && (
                                <div style={{
                                  marginTop: '1rem',
                                  padding: '0.75rem',
                                  background: 'rgba(249,206,156,0.1)',
                                  borderRadius: '8px',
                                  border: '1px solid rgba(249,206,156,0.2)',
                                }}>
                                  <div style={{ fontSize: '0.6875rem', color: '#D97706', fontWeight: 600, marginBottom: '0.375rem' }}>
                                    💡 {t('assess.suggestions')}
                                  </div>
                                  {aiFeedback.content.suggestions.map((s, i) => (
                                    <div key={i} style={{ fontSize: '0.75rem', color: '#78716C', marginBottom: '0.25rem' }}>
                                      • {s}
                                    </div>
                                  ))}
                                </div>
                              )}
                              
                              {/* 语法问题 */}
                              {aiFeedback.grammar.issues.length > 0 && (
                                <div style={{
                                  marginTop: '0.75rem',
                                  padding: '0.75rem',
                                  background: 'rgba(225,129,130,0.1)',
                                  borderRadius: '8px',
                                  border: '1px solid rgba(225,129,130,0.2)',
                                }}>
                                  <div style={{ fontSize: '0.6875rem', color: '#E18182', fontWeight: 600, marginBottom: '0.375rem' }}>
                                    ⚠️ {t('assess.grammarIssues')}
                                  </div>
                                  {aiFeedback.grammar.issues.slice(0, 3).map((issue, i) => (
                                    <div key={i} style={{ fontSize: '0.75rem', color: '#78716C', marginBottom: '0.25rem' }}>
                                      • {issue.text}: {issue.suggestion}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div style={{ 
                              textAlign: 'center', 
                              color: '#A8A29E',
                              padding: '2rem 1rem',
                            }}>
                              <span style={{ fontSize: '2rem', display: 'block', marginBottom: '0.5rem' }}>✍️</span>
                              <p style={{ fontSize: '0.8125rem' }}>
                                {t('assess.aiAnalysisHint')}
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                      
                      <button 
                        onClick={submitAssessment}
                        disabled={essay.length < 100 || submitting}
                        style={{
                          width: '100%',
                          marginTop: '1rem',
                          padding: '1rem',
                          border: 'none',
                          borderRadius: '12px',
                          background: essay.length < 100 || submitting 
                            ? '#E7E5E4' 
                            : 'linear-gradient(135deg, #F9CE9C, #E8B87A)',
                          color: essay.length < 100 || submitting ? '#A8A29E' : '#44403C',
                          fontWeight: 600,
                          cursor: essay.length < 100 || submitting ? 'not-allowed' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '0.5rem',
                          boxShadow: essay.length >= 100 && !submitting 
                            ? '0 4px 16px -4px rgba(249,206,156,0.5)' 
                            : 'none',
                          transition: 'all 0.2s ease'
                        }}
                      >
                        {submitting ? (
                          <>
                            <div className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></div>
                            {t('assess.evaluating')}
                          </>
                        ) : (
                          <>📤 {t('assess.submitEssay')}</>
                        )}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Tips Card - Enhanced */}
          {!session && !result && (
            <div className="card" style={{ 
              marginTop: '2rem',
              border: '1px solid #E7E5E4',
              background: 'linear-gradient(180deg, white, rgba(249,206,156,0.02))'
            }}>
              <div className="card-content" style={{ padding: '1.5rem' }}>
                <h3 style={{ 
                  fontSize: '1rem', 
                  marginBottom: '1.25rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  color: '#1C1917'
                }}>
                  <span style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '8px',
                    background: 'linear-gradient(135deg, #C9DDE3, #9FC5CF)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.875rem'
                  }}>📋</span>
                  {t('assess.instructions')}
                </h3>
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(3, 1fr)', 
                  gap: '1.25rem'
                }}>
                  {[
                    { 
                      icon: '🎙️', 
                      title: t('assess.communication'),
                      desc: t('assess.communicationDesc'),
                      color: '#E18182'
                    },
                    { 
                      icon: '💻', 
                      title: t('assess.programming'),
                      desc: t('assess.programmingAbilityDesc'),
                      color: '#98B8A8'
                    },
                    { 
                      icon: '✍️', 
                      title: t('assess.writing'),
                      desc: t('assess.writingAbilityDesc'),
                      color: '#F9CE9C'
                    }
                  ].map((item) => (
                    <div key={item.title} style={{
                      padding: '1rem',
                      borderRadius: '12px',
                      background: `linear-gradient(135deg, ${item.color}08, ${item.color}03)`,
                      border: `1px solid ${item.color}20`
                    }}>
                      <div style={{ 
                        fontSize: '1.5rem', 
                        marginBottom: '0.5rem' 
                      }}>
                        {item.icon}
                      </div>
                      <strong style={{ 
                        color: '#1C1917',
                        fontSize: '0.9375rem',
                        display: 'block',
                        marginBottom: '0.25rem'
                      }}>
                        {item.title}
                      </strong>
                      <p style={{ 
                        fontSize: '0.8125rem', 
                        color: '#78716C',
                        lineHeight: 1.5,
                        margin: 0
                      }}>
                        {item.desc}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {!session && !result && (
            <div className="card" style={{ marginTop: '1rem' }}>
              <div className="card-content" style={{ padding: '1.25rem' }}>
                <h3 style={{ fontSize: '1rem', marginBottom: '0.375rem', color: '#1C1917' }}>
                  {t('assessmentsList.skillCoverageTitle')}
                </h3>
                <p style={{ fontSize: '0.875rem', color: '#78716C', marginBottom: '0.75rem' }}>
                  {t('assessmentsList.skillCoverageSubtitle')}
                </p>
                <div style={{ display: 'grid', gap: '0.5rem' }}>
                  <div style={{ padding: '0.625rem 0.75rem', borderRadius: '10px', background: '#FAFAF9' }}>
                    <strong>{t('assessmentsList.coverageCommunication')}</strong>: {t('assessmentsList.coverageCommunicationDesc')}
                  </div>
                  <div style={{ padding: '0.625rem 0.75rem', borderRadius: '10px', background: '#FAFAF9' }}>
                    <strong>{t('assessmentsList.coverageCoding')}</strong>: {t('assessmentsList.coverageCodingDesc')}
                  </div>
                  <div style={{ padding: '0.625rem 0.75rem', borderRadius: '10px', background: '#FAFAF9' }}>
                    <strong>{t('assessmentsList.coverageWriting')}</strong>: {t('assessmentsList.coverageWritingDesc')}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer style={{ 
        padding: '1.5rem', 
        textAlign: 'center', 
        borderTop: '1px solid #E7E5E4',
        color: '#A8A29E',
        fontSize: '0.875rem',
        background: 'white'
      }}>
        <p>© 2026 SkillSight · HKU Skills-to-Jobs Transparency System</p>
      </footer>
      
      {/* HKU 115 Anniversary Watermark */}
      <div style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        opacity: 0.9,
        zIndex: 50,
      }}>
        <img 
          src="/hku-115.svg" 
          alt="HKU 115th Anniversary"
          style={{
            maxWidth: '140px',
            height: 'auto',
            filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.1))'
          }}
        />
      </div>
      
      {/* 成就通知 */}
      <AchievementNotification 
        achievement={recentUnlock} 
        onDismiss={dismissRecentUnlock} 
      />
      
      {/* Animations */}
      <style jsx>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.02); }
        }
        @keyframes waveAnim {
          0%, 100% { transform: scaleY(0.5); }
          50% { transform: scaleY(1); }
        }
      `}</style>
    </div>
  );
}
