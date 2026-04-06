'use client';

import { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '@/lib/contexts';
import { fmt2 } from '@/lib/formatNumber';

interface AssessmentTask {
  docId: string;
  docName: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  startedAt: number;
}

interface SkillAssessmentProgressProps {
  tasks: AssessmentTask[];
  onComplete?: () => void;
  onClose?: () => void;
}

// 可爱的完成提示组件
export function CuteCompletionNotice({ onViewSkills, onClose }: { onViewSkills: () => void; onClose: () => void }) {
  const { t } = useLanguage();
  const [showConfetti, setShowConfetti] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setShowConfetti(false), 3000);
    return () => clearTimeout(timer);
  }, []);

  const emojis = ['✨', '🌟', '🎉', '🎊', '🌈', '⭐', '💫', '🏆'];
  const messages = [
    t('assessmentProgress.cuteMessage1'),
    t('assessmentProgress.cuteMessage2'),
    t('assessmentProgress.cuteMessage3'),
    t('assessmentProgress.cuteMessage4'),
  ];
  const randomMessage = messages[Math.floor(Math.random() * messages.length)];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 2000,
        padding: '1rem',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'linear-gradient(135deg, #fef9c3 0%, #fde68a 50%, #fed7aa 100%)',
          borderRadius: '24px',
          padding: '2rem',
          maxWidth: '420px',
          width: '100%',
          textAlign: 'center',
          position: 'relative',
          boxShadow: '0 20px 60px rgba(251, 191, 36, 0.3)',
          animation: 'popIn 0.5s cubic-bezier(0.68, -0.55, 0.265, 1.55)',
        }}
      >
        {/* 飘落的表情 */}
        {showConfetti && emojis.map((emoji, i) => (
          <span
            key={i}
            style={{
              position: 'absolute',
              fontSize: '1.5rem',
              left: `${10 + i * 10}%`,
              top: '-10%',
              animation: `fall 2s ease-out ${i * 0.1}s forwards`,
              opacity: 0,
            }}
          >
            {emoji}
          </span>
        ))}

        {/* 主角图标 */}
        <div
          style={{
            width: '100px',
            height: '100px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #fde68a, #fbbf24)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '3rem',
            margin: '0 auto 1.5rem',
            boxShadow: '0 8px 24px rgba(251, 191, 36, 0.4)',
            animation: 'bounce 1s ease infinite',
          }}
        >
          🎉
        </div>

        {/* 标题 */}
        <h3
          style={{
            fontSize: '1.5rem',
            fontWeight: 700,
            color: '#92400e',
            marginBottom: '0.75rem',
          }}
        >
          {t('assessmentProgress.allDone')}
        </h3>

        {/* 可爱消息 */}
        <p
          style={{
            fontSize: '1rem',
            color: '#a16207',
            marginBottom: '1.5rem',
            lineHeight: 1.5,
          }}
        >
          {randomMessage}
        </p>

        {/* 按钮组 */}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
          <button
            onClick={onViewSkills}
            style={{
              padding: '0.875rem 1.5rem',
              borderRadius: '12px',
              border: 'none',
              background: 'linear-gradient(135deg, #fbbf24, #f59e0b)',
              color: 'white',
              fontWeight: 600,
              fontSize: '1rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              boxShadow: '0 4px 12px rgba(251, 191, 36, 0.4)',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px) scale(1.02)';
              e.currentTarget.style.boxShadow = '0 6px 20px rgba(251, 191, 36, 0.5)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0) scale(1)';
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(251, 191, 36, 0.4)';
            }}
          >
            👀 {t('assessmentProgress.viewSkills')}
          </button>
          <button
            onClick={onClose}
            style={{
              padding: '0.875rem 1.5rem',
              borderRadius: '12px',
              border: '2px solid #fcd34d',
              background: 'white',
              color: '#b45309',
              fontWeight: 500,
              fontSize: '1rem',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#fffbeb';
              e.currentTarget.style.borderColor = '#fbbf24';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'white';
              e.currentTarget.style.borderColor = '#fcd34d';
            }}
          >
            {t('common.close')}
          </button>
        </div>
      </div>

      <style jsx>{`
        @keyframes popIn {
          0% {
            transform: scale(0.5);
            opacity: 0;
          }
          100% {
            transform: scale(1);
            opacity: 1;
          }
        }
        @keyframes bounce {
          0%, 100% {
            transform: translateY(0);
          }
          50% {
            transform: translateY(-10px);
          }
        }
        @keyframes fall {
          0% {
            transform: translateY(0) rotate(0deg);
            opacity: 1;
          }
          100% {
            transform: translateY(300px) rotate(360deg);
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
}

// 进度条组件
export function SkillAssessmentProgress({ tasks, onComplete, onClose }: SkillAssessmentProgressProps) {
  const { t } = useLanguage();
  const [currentTaskIndex, setCurrentTaskIndex] = useState(0);
  const [displayProgress, setDisplayProgress] = useState(0);
  const [showCompletion, setShowCompletion] = useState(false);

  // 计算总体进度
  const totalProgress = tasks.length > 0
    ? tasks.reduce((sum, task) => sum + task.progress, 0) / (tasks.length * 100) * 100
    : 0;

  // 平滑动画进度
  useEffect(() => {
    const interval = setInterval(() => {
      setDisplayProgress((prev) => {
        const diff = totalProgress - prev;
        if (Math.abs(diff) < 0.5) return totalProgress;
        return prev + diff * 0.1;
      });
    }, 50);
    return () => clearInterval(interval);
  }, [totalProgress]);

  // 检查是否全部完成
  useEffect(() => {
    const allCompleted = tasks.length > 0 && tasks.every(t => t.status === 'completed');
    const anyFailed = tasks.some(t => t.status === 'failed');
    
    if (allCompleted && !showCompletion) {
      const timer = setTimeout(() => {
        setShowCompletion(true);
        onComplete?.();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [tasks, showCompletion, onComplete]);

  if (tasks.length === 0) return null;

  const currentTask = tasks[currentTaskIndex] || tasks[0];
  const pendingCount = tasks.filter(t => t.status === 'pending').length;
  const processingCount = tasks.filter(t => t.status === 'processing').length;
  const completedCount = tasks.filter(t => t.status === 'completed').length;

  // 获取状态图标
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return '✅';
      case 'processing': return '⏳';
      case 'failed': return '❌';
      default: return '⏸️';
    }
  };

  // 获取状态颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'var(--success)';
      case 'processing': return 'var(--warning)';
      case 'failed': return 'var(--error)';
      default: return 'var(--gray-400)';
    }
  };

  // 可爱的动物助手消息
  const getHelperMessage = () => {
    if (completedCount === tasks.length) {
      return t('assessmentProgress.helperAllDone');
    }
    if (processingCount > 0) {
      return t('assessmentProgress.helperProcessing').replace('{n}', String(processingCount));
    }
    if (pendingCount > 0) {
      return t('assessmentProgress.helperPending').replace('{n}', String(pendingCount));
    }
    return t('assessmentProgress.helperWorking');
  };

  return (
    <>
      <div
        style={{
          background: 'linear-gradient(135deg, #fefce8 0%, #fef9c3 100%)',
          border: '2px solid #fde047',
          borderRadius: '16px',
          padding: '1.25rem',
          marginBottom: '1.5rem',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* 装饰性背景元素 */}
        <div
          style={{
            position: 'absolute',
            top: '-20px',
            right: '-20px',
            width: '80px',
            height: '80px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(253, 224, 71, 0.3) 0%, transparent 70%)',
          }}
        />

        {/* 头部信息 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <span style={{ fontSize: '1.75rem' }}>🐱</span>
          <div style={{ flex: 1 }}>
            <h4 style={{ fontWeight: 600, color: '#854d0e', margin: 0, fontSize: '1rem' }}>
              {t('assessmentProgress.title')}
            </h4>
            <p style={{ fontSize: '0.8125rem', color: '#a16207', margin: '0.25rem 0 0 0' }}>
              {getHelperMessage()}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            style={{
              background: 'transparent',
              border: 'none',
              fontSize: '1.25rem',
              cursor: 'pointer',
              color: '#a8a29e',
              padding: '0.25rem',
              borderRadius: '6px',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(0,0,0,0.05)';
              e.currentTarget.style.color = '#78716c';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = '#a8a29e';
            }}
          >
            ×
          </button>
        </div>

        {/* 总体进度条 */}
        <div style={{ marginBottom: '1rem' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '0.5rem',
            }}
          >
            <span style={{ fontSize: '0.8125rem', color: '#a16207', fontWeight: 500 }}>
              {t('assessmentProgress.overallProgress')}
            </span>
            <span style={{ fontSize: '0.875rem', fontWeight: 700, color: '#854d0e' }}>
              {fmt2(displayProgress)}%
            </span>
          </div>
          <div
            style={{
              height: '12px',
              background: '#fef3c7',
              borderRadius: '10px',
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${Math.min(100, Math.max(0, displayProgress))}%`,
                background: 'linear-gradient(90deg, #fbbf24, #f59e0b)',
                borderRadius: '10px',
                transition: 'width 0.3s ease',
                position: 'relative',
              }}
            >
              {/* 闪光效果 */}
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)',
                  animation: 'shimmer 2s infinite',
                }}
              />
            </div>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginTop: '0.5rem',
              fontSize: '0.75rem',
              color: '#a8a29e',
            }}
          >
            <span>{fmt2(completedCount)}/{fmt2(tasks.length)} {t('assessmentProgress.completed')}</span>
            <span>
              {processingCount > 0 && `⏳ ${processingCount} ${t('assessmentProgress.processing')}`}
              {pendingCount > 0 && ` ⏸️ ${pendingCount} ${t('assessmentProgress.pending')}`}
            </span>
          </div>
        </div>

        {/* 当前处理的任务 */}
        {currentTask && (
          <div
            style={{
              background: 'rgba(255, 255, 255, 0.6)',
              borderRadius: '12px',
              padding: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
            }}
          >
            <span style={{ fontSize: '1.25rem' }}>{getStatusIcon(currentTask.status)}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: '0.875rem',
                  fontWeight: 500,
                  color: '#57534e',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {currentTask.docName}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#a8a29e' }}>
                {currentTask.status === 'processing' && t('assessmentProgress.analyzing')}
                {currentTask.status === 'completed' && t('assessmentProgress.done')}
                {currentTask.status === 'pending' && t('assessmentProgress.waiting')}
              </div>
            </div>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                background: `conic-gradient(${getStatusColor(currentTask.status)} ${Math.min(100, Math.max(0, currentTask.progress)) * 3.6}deg, #e5e7eb 0deg)`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: getStatusColor(currentTask.status),
                flexShrink: 0,
              }}
            >
              {fmt2(currentTask.progress)}%
            </div>
          </div>
        )}

        {/* 任务列表（可展开） */}
        {tasks.length > 1 && (
          <div style={{ marginTop: '0.75rem' }}>
            <div
              style={{
                display: 'flex',
                gap: '0.5rem',
                flexWrap: 'wrap',
              }}
            >
              {tasks.map((task, idx) => (
                <button
                  key={task.docId}
                  onClick={() => setCurrentTaskIndex(idx)}
                  style={{
                    padding: '0.375rem 0.625rem',
                    borderRadius: '8px',
                    border: '1px solid',
                    borderColor: idx === currentTaskIndex ? '#fbbf24' : '#e5e7eb',
                    background: idx === currentTaskIndex ? '#fef3c7' : 'white',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.375rem',
                    color: idx === currentTaskIndex ? '#92400e' : '#57534e',
                  }}
                >
                  <span>{getStatusIcon(task.status)}</span>
                  <span
                    style={{
                      maxWidth: '80px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {task.docName}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        <style jsx>{`
          @keyframes shimmer {
            0% {
              transform: translateX(-100%);
            }
            100% {
              transform: translateX(100%);
            }
          }
        `}</style>
      </div>

      {/* 完成提示弹窗 */}
      {showCompletion && (
        <CuteCompletionNotice
          onViewSkills={() => {
            setShowCompletion(false);
            onComplete?.();
          }}
          onClose={() => setShowCompletion(false)}
        />
      )}
    </>
  );
}

export default SkillAssessmentProgress;
