'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useLanguage } from '@/lib/contexts';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

interface PublicSkill {
  skill_id: string;
  canonical_name: string;
  level: number;
  label: string;
}

interface PublicProfile {
  subject_id: string;
  skills_count: number;
  verified_count: number;
  top_skills: PublicSkill[];
  generated_at: string;
}

export default function ProfileClient() {
  const params = useParams();
  const userId = params.userId as string;
  const { t } = useLanguage();
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!userId) return;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/public/profile/${encodeURIComponent(userId)}`);
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        setProfile(data);
      } catch {
        setError('Profile not found or unavailable.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [userId]);

  const getLevelLabel = (level: number) => {
    if (level >= 3) return 'Expert';
    if (level >= 2) return 'Demonstrated';
    if (level >= 1) return 'Mentioned';
    return 'Assessed';
  };

  const getLevelColor = (level: number) => {
    if (level >= 3) return '#E18182';
    if (level >= 2) return '#98B8A8';
    if (level >= 1) return '#F9CE9C';
    return '#C9DDE3';
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #BBCFC3 0%, #C9DDE3 50%, #F9CE9C 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem',
    }}>
      <div style={{
        maxWidth: '560px',
        width: '100%',
        background: 'rgba(255,255,255,0.95)',
        borderRadius: '24px',
        padding: '2.5rem',
        boxShadow: '0 20px 60px rgba(0,0,0,0.1)',
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#78716C' }}>
            {t('common.loading')}
          </div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '3rem' }}>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔒</div>
            <h2 style={{ color: '#44403C', marginBottom: '0.5rem' }}>Profile Unavailable</h2>
            <p style={{ color: '#78716C' }}>{error}</p>
          </div>
        ) : profile ? (
          <>
            <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
              <div style={{
                width: '80px', height: '80px', borderRadius: '50%',
                background: 'linear-gradient(135deg, #E18182, #F9CE9C)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 1rem', fontSize: '2rem', color: 'white',
              }}>
                {profile.subject_id.charAt(0).toUpperCase()}
              </div>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1C1917', marginBottom: '0.25rem' }}>
                {profile.subject_id}
              </h1>
              <p style={{ color: '#78716C', fontSize: '0.875rem' }}>
                SkillSight Verified Profile
              </p>
            </div>

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', marginBottom: '2rem' }}>
              <div style={{ textAlign: 'center', padding: '1rem 1.5rem', background: '#f5f5f4', borderRadius: '12px' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#E18182' }}>{profile.verified_count}</div>
                <div style={{ fontSize: '0.75rem', color: '#78716C' }}>Verified Skills</div>
              </div>
              <div style={{ textAlign: 'center', padding: '1rem 1.5rem', background: '#f5f5f4', borderRadius: '12px' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#98B8A8' }}>{profile.skills_count}</div>
                <div style={{ fontSize: '0.75rem', color: '#78716C' }}>Total Skills</div>
              </div>
            </div>

            {profile.top_skills.length > 0 && (
              <div>
                <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#44403C', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Top Skills
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {profile.top_skills.map((skill) => (
                    <div key={skill.skill_id} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '0.75rem 1rem', background: '#fafaf9', borderRadius: '10px',
                      border: '1px solid #e7e5e4',
                    }}>
                      <span style={{ fontWeight: 500, color: '#1C1917' }}>{skill.canonical_name}</span>
                      <span style={{
                        padding: '0.25rem 0.75rem', borderRadius: '20px', fontSize: '0.75rem', fontWeight: 600,
                        background: getLevelColor(skill.level) + '20', color: getLevelColor(skill.level),
                      }}>
                        {getLevelLabel(skill.level)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ marginTop: '2rem', textAlign: 'center', fontSize: '0.75rem', color: '#a8a29e' }}>
              Verified by SkillSight · {new Date(profile.generated_at).toLocaleDateString()}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
