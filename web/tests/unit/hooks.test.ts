import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('@/lib/api', () => ({ API_BASE_URL: 'http://localhost:8001' }));
vi.mock('@/lib/bffClient', () => ({
  getToken: () => 'mock-token',
  studentBff: {
    getAchievements: vi.fn().mockResolvedValue({ achievements: [], totalPoints: 0, recentUnlock: null }),
    postAchievementProgress: vi.fn().mockResolvedValue({}),
  },
}));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn() },
}));

describe('useWritingAnalyzer', () => {
  it('analyzes basic text statistics', async () => {
    const { useWritingAnalyzer } = await import('@/lib/hooks');
    const { result } = renderHook(() => useWritingAnalyzer());

    expect(result.current.analysis).toBeNull();
    expect(result.current.isAnalyzing).toBe(false);
  });

  it('computes word count and sentence count', async () => {
    const { useWritingAnalyzer } = await import('@/lib/hooks');
    const { result } = renderHook(() => useWritingAnalyzer());

    act(() => {
      result.current.analyzeText('Hello world. This is a test sentence. Another one here.');
    });

    await vi.waitFor(() => {
      expect(result.current.analysis).not.toBeNull();
    });

    expect(result.current.analysis!.wordCount).toBe(10);
    expect(result.current.analysis!.sentenceCount).toBe(3);
    expect(result.current.analysis!.paragraphCount).toBe(1);
  });

  it('detects grammar issues like double spaces', async () => {
    const { useWritingAnalyzer } = await import('@/lib/hooks');
    const { result } = renderHook(() => useWritingAnalyzer());

    act(() => {
      result.current.analyzeText('Hello  world.  Too many spaces here.');
    });

    await vi.waitFor(() => {
      expect(result.current.analysis).not.toBeNull();
    });

    const grammarFeedback = result.current.analysis!.feedback.filter(f => f.type === 'grammar');
    expect(grammarFeedback.length).toBeGreaterThan(0);
  });
});

describe('useLocalStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns initial value when localStorage is empty', async () => {
    const { useLocalStorage } = await import('@/lib/hooks');
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));

    expect(result.current[0]).toBe('default');
    expect(result.current[2]).toBe(true);
  });

  it('persists value to localStorage', async () => {
    const { useLocalStorage } = await import('@/lib/hooks');
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));

    act(() => {
      result.current[1]('new-value');
    });

    expect(result.current[0]).toBe('new-value');
    expect(localStorage.getItem('test-key')).toBe(JSON.stringify('new-value'));
  });

  it('reads saved value from localStorage', async () => {
    localStorage.setItem('saved-key', JSON.stringify({ a: 1 }));
    const { useLocalStorage } = await import('@/lib/hooks');
    const { result } = renderHook(() => useLocalStorage('saved-key', {}));

    await vi.waitFor(() => {
      expect(result.current[2]).toBe(true);
    });
    expect(result.current[0]).toEqual({ a: 1 });
  });
});

describe('useKeystrokeTracker', () => {
  it('initializes with zero counts', async () => {
    const { useKeystrokeTracker } = await import('@/lib/hooks');
    const { result } = renderHook(() => useKeystrokeTracker());

    expect(result.current.keystrokeData.totalKeystrokes).toBe(0);
    expect(result.current.keystrokeData.pasteCount).toBe(0);
    expect(result.current.keystrokeData.deleteCount).toBe(0);
    expect(result.current.keystrokeData.suspiciousActivity).toBe(false);
  });

  it('tracks paste events', async () => {
    const { useKeystrokeTracker } = await import('@/lib/hooks');
    const { result } = renderHook(() => useKeystrokeTracker());

    act(() => {
      result.current.handlePaste();
      result.current.handlePaste();
    });

    expect(result.current.keystrokeData.pasteCount).toBe(2);
  });

  it('resets all counts', async () => {
    const { useKeystrokeTracker } = await import('@/lib/hooks');
    const { result } = renderHook(() => useKeystrokeTracker());

    act(() => {
      result.current.handlePaste();
    });
    expect(result.current.keystrokeData.pasteCount).toBe(1);

    act(() => {
      result.current.reset();
    });
    expect(result.current.keystrokeData.pasteCount).toBe(0);
    expect(result.current.keystrokeData.totalKeystrokes).toBe(0);
  });
});
