'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

// SkillSight Logo - 代表技能洞察与成长的创意设计
const SkillSightLogo = ({ size = 80 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path 
      d="M16 6C8 6 2 16 2 16C2 16 8 26 16 26C24 26 30 16 30 16C30 16 24 6 16 6Z" 
      fill="url(#eyeGradientHome)" 
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
      <linearGradient id="eyeGradientHome" x1="2" y1="16" x2="30" y2="16" gradientUnits="userSpaceOnUse">
        <stop stopColor="#F9CE9C"/>
        <stop offset="0.5" stopColor="#E18182"/>
        <stop offset="1" stopColor="#C9DDE3"/>
      </linearGradient>
    </defs>
  </svg>
);

export default function Home() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  
  useEffect(() => {
    setMounted(true);
    try {
      const user = localStorage.getItem('user');
      const token = localStorage.getItem('auth_token');
      if (user && token) {
        try {
          const userData = JSON.parse(user);
          router.push(userData.role === 'admin' ? '/admin' : '/dashboard');
        } catch {
          localStorage.removeItem('user');
          router.push('/login');
        }
      } else {
        localStorage.removeItem('user');
        localStorage.removeItem('auth_token');
        router.push('/login');
      }
    } catch (e) {
      console.warn('Failed to read auth state from localStorage:', e);
      router.push('/login');
    }
  }, [router]);

  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      background: `
        radial-gradient(ellipse at 20% 20%, rgba(249, 206, 156, 0.4) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 80%, rgba(201, 221, 227, 0.4) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 50%, rgba(225, 129, 130, 0.2) 0%, transparent 50%),
        linear-gradient(135deg, #BBCFC3 0%, #C9DDE3 50%, #F9CE9C 100%)
      `,
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Animated background elements */}
      <div style={{
        position: 'absolute',
        top: '-50%',
        left: '-50%',
        width: '200%',
        height: '200%',
        background: `
          radial-gradient(circle at 30% 30%, rgba(249, 206, 156, 0.3) 0%, transparent 30%),
          radial-gradient(circle at 70% 70%, rgba(201, 221, 227, 0.3) 0%, transparent 30%)
        `,
        animation: 'floatBg 20s ease-in-out infinite',
        pointerEvents: 'none'
      }} />

      <div style={{ 
        textAlign: 'center', 
        color: '#1C1917',
        zIndex: 1,
        opacity: mounted ? 1 : 0,
        transform: mounted ? 'translateY(0)' : 'translateY(20px)',
        transition: 'all 0.6s ease'
      }}>
        <div style={{ 
          marginBottom: '1.5rem',
          display: 'flex',
          justifyContent: 'center'
        }}>
          <div style={{
            background: 'rgba(255,255,255,0.9)',
            borderRadius: '24px',
            padding: '1rem',
            boxShadow: '0 8px 32px -8px rgba(225, 129, 130, 0.4)'
          }}>
            <SkillSightLogo size={80} />
          </div>
        </div>
        <h1 style={{ 
          fontSize: '2.5rem', 
          marginBottom: '0.5rem',
          fontWeight: 700
        }}>SkillSight</h1>
        <p style={{ 
          opacity: 0.7,
          fontSize: '1rem'
        }}>HKU Skills-to-Jobs Transparency System</p>
        <div style={{
          marginTop: '2rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.5rem'
        }}>
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: '#E18182',
            animation: 'loadingDot 1.4s infinite ease-in-out both',
            animationDelay: '0s'
          }} />
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: '#F9CE9C',
            animation: 'loadingDot 1.4s infinite ease-in-out both',
            animationDelay: '0.16s'
          }} />
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: '#BBCFC3',
            animation: 'loadingDot 1.4s infinite ease-in-out both',
            animationDelay: '0.32s'
          }} />
        </div>
      </div>

      {/* HKU 115 Anniversary Watermark */}
      <div style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        opacity: 0.9,
        zIndex: 50,
        transition: 'all 0.3s ease',
        cursor: 'pointer'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.opacity = '1';
        e.currentTarget.style.transform = 'scale(1.05)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.opacity = '0.9';
        e.currentTarget.style.transform = 'scale(1)';
      }}
      >
        <img 
          src="/hku-115.svg" 
          alt="HKU 115th Anniversary"
          style={{
            maxWidth: '180px',
            height: 'auto',
            filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.1))'
          }}
        />
      </div>

      <style jsx>{`
        @keyframes loadingDot {
          0%, 80%, 100% {
            transform: scale(0.6);
            opacity: 0.5;
          }
          40% {
            transform: scale(1);
            opacity: 1;
          }
        }
        @keyframes floatBg {
          0%, 100% { transform: translate(0, 0) rotate(0deg); }
          33% { transform: translate(2%, 2%) rotate(1deg); }
          66% { transform: translate(-1%, 1%) rotate(-1deg); }
        }
      `}</style>
    </div>
  );
}
