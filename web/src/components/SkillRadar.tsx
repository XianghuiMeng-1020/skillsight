'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useLanguage } from '@/lib/contexts';

interface SkillData {
  name: string;
  value: number; // 0-100
  targetValue?: number;
  peerValue?: number;
}

interface SkillRadarProps {
  skills: SkillData[];
  size?: number;
  showLegend?: boolean;
  showComparison?: boolean;
}

export function SkillRadar({
  skills,
  size = 300,
  showLegend = true,
  showComparison = false
}: SkillRadarProps) {
  const { t } = useLanguage();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartSummary = useMemo(
    () =>
      skills
        .slice(0, 6)
        .map((s) => `${s.name}: ${Math.round(s.value)}`)
        .join(', '),
    [skills]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || skills.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // High DPI support
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const centerX = size / 2;
    const centerY = size / 2;
    const radius = (size - 60) / 2;
    const angleStep = (Math.PI * 2) / skills.length;

    // Clear canvas
    ctx.clearRect(0, 0, size, size);

    // Draw concentric circles (grid)
    const levels = 4;
    for (let i = 1; i <= levels; i++) {
      const r = (radius / levels) * i;
      ctx.beginPath();
      ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
      ctx.strokeStyle = i === levels ? '#E7E5E4' : '#F5F5F4';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Draw radial lines and labels
    skills.forEach((skill, i) => {
      const angle = angleStep * i - Math.PI / 2;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;

      // Radial line
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(x, y);
      ctx.strokeStyle = '#E7E5E4';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Label
      const labelX = centerX + Math.cos(angle) * (radius + 25);
      const labelY = centerY + Math.sin(angle) * (radius + 25);
      ctx.font = '11px Inter, sans-serif';
      ctx.fillStyle = '#57534E';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      
      // Truncate long names
      const displayName = skill.name.length > 10 
        ? skill.name.slice(0, 9) + '…' 
        : skill.name;
      ctx.fillText(displayName, labelX, labelY);
    });

    // Helper function to draw polygon
    const drawPolygon = (values: number[], color: string, fillAlpha: number, lineWidth: number) => {
      ctx.beginPath();
      values.forEach((value, i) => {
        const angle = angleStep * i - Math.PI / 2;
        const r = (value / 100) * radius;
        const x = centerX + Math.cos(angle) * r;
        const y = centerY + Math.sin(angle) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();

      // Fill
      const rgbMatch = color.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
      if (rgbMatch) {
        const r = parseInt(rgbMatch[1], 16);
        const g = parseInt(rgbMatch[2], 16);
        const b = parseInt(rgbMatch[3], 16);
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${fillAlpha})`;
        ctx.fill();
      }

      // Stroke
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      ctx.stroke();

      // Draw points
      values.forEach((value, i) => {
        const angle = angleStep * i - Math.PI / 2;
        const r = (value / 100) * radius;
        const x = centerX + Math.cos(angle) * r;
        const y = centerY + Math.sin(angle) * r;

        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    };

    // Draw comparison data first (behind)
    if (showComparison) {
      // Target values
      const targetValues = skills.map(s => s.targetValue || 0);
      if (targetValues.some(v => v > 0)) {
        drawPolygon(targetValues, '#F9CE9C', 0.15, 2);
      }

      // Peer values
      const peerValues = skills.map(s => s.peerValue || 0);
      if (peerValues.some(v => v > 0)) {
        drawPolygon(peerValues, '#C9DDE3', 0.15, 2);
      }
    }

    // Draw main values (on top)
    const mainValues = skills.map(s => s.value);
    drawPolygon(mainValues, '#E18182', 0.25, 3);

  }, [skills, size, showComparison]);

  if (skills.length < 3) {
    return (
      <div style={{
        width: size,
        height: size,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--gray-50)',
        borderRadius: 'var(--radius-lg)',
        color: 'var(--gray-500)',
        fontSize: '0.875rem'
      }}>
        {t('skills.minRequired')}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
      <canvas 
        ref={canvasRef} 
        style={{ width: size, height: size }}
        role="img"
        aria-label={`${t('skills.radarTitle')}: ${chartSummary}`}
      />
      
      {showLegend && (
        <div style={{ 
          display: 'flex', 
          gap: '1.5rem', 
          fontSize: '0.75rem',
          color: 'var(--gray-600)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <div style={{ 
              width: '12px', 
              height: '12px', 
              borderRadius: '50%', 
              background: '#E18182' 
            }} />
            <span>{t('skills.yourLevel')}</span>
          </div>
          {showComparison && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  background: '#F9CE9C'
                }} />
                <span>{t('skills.targetLevel')}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  background: '#C9DDE3'
                }} />
                <span>{t('skills.peerAvg')}</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
