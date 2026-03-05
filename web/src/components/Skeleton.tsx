'use client';

interface SkeletonProps {
  width?: string;
  height?: string;
  borderRadius?: string;
  className?: string;
}

export function Skeleton({ 
  width = '100%', 
  height = '1rem', 
  borderRadius = '4px',
  className = ''
}: SkeletonProps) {
  return (
    <div
      className={className}
      style={{
        width,
        height,
        borderRadius,
        background: 'linear-gradient(90deg, var(--gray-200) 25%, var(--gray-100) 50%, var(--gray-200) 75%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s infinite',
      }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div style={{ 
      background: 'var(--white)',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid var(--gray-200)',
      padding: '1.5rem',
    }}>
      <Skeleton width="40%" height="1.25rem" />
      <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <Skeleton height="0.875rem" />
        <Skeleton height="0.875rem" width="80%" />
        <Skeleton height="0.875rem" width="60%" />
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div 
          key={i} 
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '1rem',
            padding: '0.875rem 1rem',
            background: i % 2 === 0 ? 'var(--gray-50)' : 'transparent',
            borderRadius: 'var(--radius)',
          }}
        >
          <Skeleton width="24px" height="24px" borderRadius="4px" />
          <Skeleton width="40%" />
          <Skeleton width="20%" />
          <Skeleton width="15%" />
        </div>
      ))}
    </div>
  );
}

// Add shimmer animation to globals.css
// @keyframes shimmer {
//   0% { background-position: -200% 0; }
//   100% { background-position: 200% 0; }
// }
