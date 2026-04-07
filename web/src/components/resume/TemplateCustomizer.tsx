'use client';

import { useEffect, useState } from 'react';

interface TemplateCustomizerProps {
  onChange: (opts: Record<string, unknown>) => void;
}

export default function TemplateCustomizer({ onChange }: TemplateCustomizerProps) {
  const [themeColor, setThemeColor] = useState('#0f766e');
  const [fontScale, setFontScale] = useState(1);

  useEffect(() => {
    onChange({ themeColor, fontScale });
  }, [themeColor, fontScale, onChange]);

  return (
    <div style={{ border: '1px solid var(--gray-200)', borderRadius: 12, padding: '0.75rem', marginBottom: '0.75rem', background: '#fff' }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Template Customizer</div>
      <label style={{ display: 'block', fontSize: 12, marginBottom: 6 }}>
        Theme Color
        <input type="color" value={themeColor} onChange={(e) => setThemeColor(e.target.value)} style={{ marginLeft: 8 }} />
      </label>
      <label style={{ display: 'block', fontSize: 12 }}>
        Font Scale: {fontScale.toFixed(2)}x
        <input type="range" min={0.9} max={1.15} step={0.01} value={fontScale} onChange={(e) => setFontScale(Number(e.target.value))} style={{ width: '100%' }} />
      </label>
    </div>
  );
}
