'use client';

import { useEffect, useState, useRef } from 'react';
import { useLocalStorage } from '@/lib/hooks';
import { useLanguage, getDateLocale } from '@/lib/contexts';
import { fmt2 } from '@/lib/formatNumber';

interface AssessmentRecord {
  id: string;
  type: 'communication' | 'programming' | 'writing';
  score: number;
  level: string;
  date: string;
  details?: Record<string, number>;
}

interface AssessmentHistoryProps {
  onSelectRecord?: (record: AssessmentRecord) => void;
}

const typeConfigKeys = {
  communication: 'assess.communication',
  programming: 'assess.programming',
  writing: 'assess.writing',
} as const;

export function AssessmentHistory({ onSelectRecord }: AssessmentHistoryProps) {
  const { t, language } = useLanguage();
  const [history, setHistory] = useLocalStorage<AssessmentRecord[]>('skillsight-assessment-history', []);
  const [selectedType, setSelectedType] = useState<'all' | 'communication' | 'programming' | 'writing'>('all');

  const filteredHistory = history.filter(
    record => selectedType === 'all' || record.type === selectedType
  );

  const typeConfig = {
    communication: { icon: '🎙️', color: '#E18182', labelKey: typeConfigKeys.communication } as const,
    programming: { icon: '💻', color: '#98B8A8', labelKey: typeConfigKeys.programming } as const,
    writing: { icon: '✍️', color: '#F9CE9C', labelKey: typeConfigKeys.writing } as const,
  };

  return (
    <div>
      {/* Filter Tabs */}
      <div style={{ 
        display: 'flex', 
        gap: '0.5rem', 
        marginBottom: '1rem',
        flexWrap: 'wrap'
      }}>
        {(['all', 'communication', 'programming', 'writing'] as const).map(type => (
          <button
            key={type}
            onClick={() => setSelectedType(type)}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '9999px',
              border: selectedType === type ? '2px solid var(--coral)' : '1px solid var(--gray-200)',
              background: selectedType === type ? 'var(--coral-50)' : 'white',
              color: selectedType === type ? 'var(--coral)' : 'var(--gray-600)',
              cursor: 'pointer',
              fontSize: '0.875rem',
              fontWeight: 500,
              transition: 'all 0.2s ease'
            }}
          >
            {type === 'all' ? `📊 ${t('skills.all')}` : `${typeConfig[type].icon} ${t(typeConfig[type].labelKey)}`}
          </button>
        ))}
      </div>

      {/* History List */}
      {filteredHistory.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '3rem 2rem',
          color: 'var(--gray-500)'
        }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem', opacity: 0.5 }}>📋</div>
          <div style={{ fontWeight: 500, marginBottom: '0.5rem' }}>{t('assess.noHistory')}</div>
          <div style={{ fontSize: '0.875rem' }}>{t('assess.noHistoryDesc')}</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {filteredHistory.map(record => {
            const config = typeConfig[record.type];
            return (
              <div
                key={record.id}
                onClick={() => onSelectRecord?.(record)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                  padding: '1rem',
                  background: 'var(--gray-50)',
                  borderRadius: 'var(--radius)',
                  cursor: onSelectRecord ? 'pointer' : 'default',
                  transition: 'all 0.2s ease',
                  border: '1px solid transparent'
                }}
                onMouseEnter={e => {
                  if (onSelectRecord) {
                    e.currentTarget.style.borderColor = 'var(--gray-200)';
                    e.currentTarget.style.transform = 'translateX(4px)';
                  }
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = 'transparent';
                  e.currentTarget.style.transform = 'translateX(0)';
                }}
              >
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: 'var(--radius)',
                  background: `linear-gradient(135deg, ${config.color}20, ${config.color}40)`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '1.5rem'
                }}>
                  {config.icon}
                </div>
                
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, color: 'var(--gray-900)' }}>
                    {t(config.labelKey)}{t('assess.assessmentSuffix')}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                    {new Date(record.date).toLocaleDateString(getDateLocale(language), {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </div>
                </div>
                
                <div style={{ textAlign: 'right' }}>
                  <div style={{ 
                    fontSize: '1.5rem', 
                    fontWeight: 700,
                    color: config.color
                  }}>
                    {fmt2(record.score)}
                  </div>
                  <div style={{
                    fontSize: '0.75rem',
                    padding: '0.125rem 0.5rem',
                    borderRadius: '9999px',
                    background: `${config.color}20`,
                    color: config.color
                  }}>
                    {record.level}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Progress Chart Component
export function ProgressChart({ history }: { history: AssessmentRecord[] }) {
  const { t } = useLanguage();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || history.length < 2) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = 400;
    const height = 200;
    const padding = 40;

    // High DPI
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Sort by date
    const sorted = [...history].sort((a, b) => 
      new Date(a.date).getTime() - new Date(b.date).getTime()
    );

    const maxScore = 100;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    // Draw axes
    ctx.strokeStyle = '#E7E5E4';
    ctx.lineWidth = 1;
    
    // Y axis
    ctx.beginPath();
    ctx.moveTo(padding, padding);
    ctx.lineTo(padding, height - padding);
    ctx.stroke();
    
    // X axis
    ctx.beginPath();
    ctx.moveTo(padding, height - padding);
    ctx.lineTo(width - padding, height - padding);
    ctx.stroke();

    // Y axis labels
    ctx.font = '10px Inter';
    ctx.fillStyle = '#78716C';
    ctx.textAlign = 'right';
    [0, 25, 50, 75, 100].forEach(val => {
      const y = height - padding - (val / maxScore) * chartHeight;
      ctx.fillText(val.toString(), padding - 8, y + 3);
      
      // Grid line
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(width - padding, y);
      ctx.strokeStyle = '#F5F5F4';
      ctx.stroke();
    });

    // Draw line chart
    const stepX = chartWidth / (sorted.length - 1);
    
    // Gradient fill under line
    const gradient = ctx.createLinearGradient(0, padding, 0, height - padding);
    gradient.addColorStop(0, 'rgba(225, 129, 130, 0.3)');
    gradient.addColorStop(1, 'rgba(225, 129, 130, 0)');

    ctx.beginPath();
    ctx.moveTo(padding, height - padding);
    sorted.forEach((record, i) => {
      const x = padding + i * stepX;
      const y = height - padding - (record.score / maxScore) * chartHeight;
      ctx.lineTo(x, y);
    });
    ctx.lineTo(padding + (sorted.length - 1) * stepX, height - padding);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw line
    ctx.beginPath();
    sorted.forEach((record, i) => {
      const x = padding + i * stepX;
      const y = height - padding - (record.score / maxScore) * chartHeight;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#E18182';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();

    // Draw points
    sorted.forEach((record, i) => {
      const x = padding + i * stepX;
      const y = height - padding - (record.score / maxScore) * chartHeight;
      
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = '#E18182';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.stroke();
    });

  }, [history]);

  if (history.length < 2) {
    return (
      <div style={{
        textAlign: 'center',
        padding: '2rem',
        color: 'var(--gray-500)',
        fontSize: '0.875rem'
      }}>
        {t('assess.needMoreHistory')}
      </div>
    );
  }

  return (
    <div>
      <h4 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <span>📈</span> {t('assess.progressCurve')}
      </h4>
      <canvas 
        ref={canvasRef} 
        style={{ width: '100%', maxWidth: '400px', height: '200px' }}
      />
    </div>
  );
}

// Hook to save assessment results
export function useSaveAssessment() {
  const [history, setHistory] = useLocalStorage<AssessmentRecord[]>('skillsight-assessment-history', []);

  const saveAssessment = (
    type: 'communication' | 'programming' | 'writing',
    score: number,
    level: string,
    details?: Record<string, number>
  ) => {
    const record: AssessmentRecord = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type,
      score,
      level,
      date: new Date().toISOString(),
      details
    };
    
    setHistory(prev => [record, ...prev].slice(0, 50)); // Keep last 50
    return record;
  };

  return { history, saveAssessment };
}
