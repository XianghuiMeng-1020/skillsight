'use client';

import { useState, useEffect } from 'react';

export const SkillSightLogo = ({ size = 28 }: { size?: number }) => (
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

export const ScoreCircle = ({ score, label, color = '#E18182' }: { score: number; label: string; color?: string }) => {
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

export const ScoreBar = ({ label, score, icon, color }: { label: string; score: number; icon: string; color: string }) => (
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

export const LevelBadge = ({ level, label }: { level: string; label: string }) => {
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
