'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { getToken } from '@/lib/bffClient';
import { logger } from '@/lib/logger';

// ==========================================
// 1. 音频录制 Hook (Web Audio API)
// ==========================================
export interface AudioRecorderState {
  isRecording: boolean;
  isPaused: boolean;
  audioBlob: Blob | null;
  audioUrl: string | null;
  duration: number;
  error: string | null;
  audioLevel: number;
}

export interface AudioRecorderActions {
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob | null>;
  pauseRecording: () => void;
  resumeRecording: () => void;
  resetRecording: () => void;
}

export function useAudioRecorder(): AudioRecorderState & AudioRecorderActions {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // 清理函数
  const cleanup = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }
  }, []);

  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  // 分析音频级别
  const analyzeAudioLevel = useCallback(() => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
    setAudioLevel(average / 255);

    if (isRecording && !isPaused) {
      animationFrameRef.current = requestAnimationFrame(analyzeAudioLevel);
    }
  }, [isRecording, isPaused]);

  const startRecording = async () => {
    try {
      setError(null);
      audioChunksRef.current = [];

      // 请求麦克风权限
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100,
        },
      });

      streamRef.current = stream;

      // 创建音频分析器
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      analyserRef.current = analyser;

      // 创建 MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onerror = (event) => {
        setError('录音出错: ' + (event as ErrorEvent).message);
        setIsRecording(false);
      };

      mediaRecorder.start(100); // 每100ms收集一次数据
      setIsRecording(true);
      setIsPaused(false);
      startTimeRef.current = Date.now();

      // 开始计时
      timerRef.current = setInterval(() => {
        if (!isPaused) {
          setDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
        }
      }, 100);

      // 开始分析音频级别
      analyzeAudioLevel();
    } catch (err) {
      const message = err instanceof Error ? err.message : '无法访问麦克风';
      setError(message);
      logger.error('录音错误', err);
    }
  };

  const stopRecording = async (): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') {
        resolve(null);
        return;
      }

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        setAudioBlob(blob);
        setAudioUrl(url);
        setIsRecording(false);
        setIsPaused(false);

        cleanup();
        resolve(blob);
      };

      mediaRecorderRef.current.stop();
    });
  };

  const pauseRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.pause();
      setIsPaused(true);
    }
  };

  const resumeRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'paused') {
      mediaRecorderRef.current.resume();
      setIsPaused(false);
      analyzeAudioLevel();
    }
  };

  const resetRecording = () => {
    cleanup();
    setIsRecording(false);
    setIsPaused(false);
    setAudioBlob(null);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setAudioUrl(null);
    setDuration(0);
    setError(null);
    setAudioLevel(0);
    audioChunksRef.current = [];
  };

  return {
    isRecording,
    isPaused,
    audioBlob,
    audioUrl,
    duration,
    error,
    audioLevel,
    startRecording,
    stopRecording,
    pauseRecording,
    resumeRecording,
    resetRecording,
  };
}

// ==========================================
// 2. 代码执行 Hook (使用 Pyodide 或 JS)
// ==========================================
export interface CodeExecutionResult {
  output: string;
  error: string | null;
  executionTime: number;
  testResults?: {
    name: string;
    passed: boolean;
    expected: string;
    actual: string;
  }[];
}

export interface CodeExecutorState {
  isExecuting: boolean;
  result: CodeExecutionResult | null;
  pyodideLoaded: boolean;
}

export interface CodeExecutorActions {
  executeCode: (code: string, language: string, testCases?: TestCase[]) => Promise<CodeExecutionResult>;
  loadPyodide: () => Promise<void>;
}

export interface TestCase {
  input: Record<string, unknown>;
  expected: unknown;
  name?: string;
}

// Pyodide 类型声明
declare global {
  interface Window {
    loadPyodide?: (config: { indexURL: string }) => Promise<PyodideInterface>;
    pyodide?: PyodideInterface;
  }
}

interface PyodideInterface {
  runPythonAsync: (code: string) => Promise<unknown>;
  globals: {
    get: (name: string) => unknown;
    set: (name: string, value: unknown) => void;
  };
}

export function useCodeExecutor(): CodeExecutorState & CodeExecutorActions {
  const [isExecuting, setIsExecuting] = useState(false);
  const [result, setResult] = useState<CodeExecutionResult | null>(null);
  const [pyodideLoaded, setPyodideLoaded] = useState(false);
  const pyodideRef = useRef<PyodideInterface | null>(null);

  // 加载 Pyodide（浏览器中运行 Python）
  const loadPyodide = async () => {
    if (pyodideRef.current || pyodideLoaded) return;

    try {
      // 动态加载 Pyodide
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/pyodide/v0.24.1/full/pyodide.js';
      script.async = true;
      
      await new Promise<void>((resolve, reject) => {
        script.onload = async () => {
          try {
            if (window.loadPyodide) {
              const pyodide = await window.loadPyodide({
                indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.24.1/full/',
              });
              pyodideRef.current = pyodide;
              window.pyodide = pyodide;
              setPyodideLoaded(true);
              resolve();
            }
          } catch (err) {
            reject(err);
          }
        };
        script.onerror = reject;
      });

      document.head.appendChild(script);
    } catch (err) {
      logger.error('Failed to load Pyodide', err);
    }
  };

  // 执行 JavaScript 代码
  const executeJavaScript = async (code: string, testCases?: TestCase[]): Promise<CodeExecutionResult> => {
    const startTime = performance.now();
    const logs: string[] = [];

    // 重写 console.log 来捕获输出
    const originalLog = console.log;
    console.log = (...args) => {
      logs.push(args.map(arg => 
        typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
      ).join(' '));
    };

    try {
      // 使用 Function 构造器执行代码
      const wrappedCode = `
        "use strict";
        ${code}
      `;
      
      // eslint-disable-next-line no-new-func
      const fn = new Function(wrappedCode);
      const result = fn();

      const executionTime = performance.now() - startTime;

      // 运行测试用例
      let testResults;
      if (testCases && testCases.length > 0) {
        testResults = [];
        for (let i = 0; i < testCases.length; i++) {
          const tc = testCases[i];
          try {
            // 提取函数名并调用
            const funcMatch = code.match(/function\s+(\w+)/);
            if (funcMatch) {
              const funcName = funcMatch[1];
              // eslint-disable-next-line no-new-func
              const testFn = new Function(`
                ${code}
                return ${funcName}(...Object.values(${JSON.stringify(tc.input)}));
              `);
              const actual = testFn();
              testResults.push({
                name: tc.name || `Test ${i + 1}`,
                passed: JSON.stringify(actual) === JSON.stringify(tc.expected),
                expected: JSON.stringify(tc.expected),
                actual: JSON.stringify(actual),
              });
            }
          } catch (err) {
            testResults.push({
              name: tc.name || `Test ${i + 1}`,
              passed: false,
              expected: JSON.stringify(tc.expected),
              actual: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
            });
          }
        }
      }

      console.log = originalLog;

      return {
        output: logs.join('\n') || (result !== undefined ? String(result) : ''),
        error: null,
        executionTime,
        testResults,
      };
    } catch (err) {
      console.log = originalLog;
      return {
        output: logs.join('\n'),
        error: err instanceof Error ? err.message : 'Unknown error',
        executionTime: performance.now() - startTime,
      };
    }
  };

  // 执行 Python 代码
  const executePython = async (code: string, testCases?: TestCase[]): Promise<CodeExecutionResult> => {
    const startTime = performance.now();

    if (!pyodideRef.current) {
      await loadPyodide();
    }

    if (!pyodideRef.current) {
      return {
        output: '',
        error: 'Python runtime not loaded. Please wait...',
        executionTime: 0,
      };
    }

    try {
      // 捕获 stdout
      await pyodideRef.current.runPythonAsync(`
import sys
from io import StringIO
sys.stdout = StringIO()
      `);

      // 执行用户代码
      await pyodideRef.current.runPythonAsync(code);

      // 获取输出
      const output = await pyodideRef.current.runPythonAsync(`
sys.stdout.getvalue()
      `);

      const executionTime = performance.now() - startTime;

      // 运行测试用例
      let testResults;
      if (testCases && testCases.length > 0) {
        testResults = [];
        for (let i = 0; i < testCases.length; i++) {
          const tc = testCases[i];
          try {
            // 提取函数名并调用
            const funcMatch = code.match(/def\s+(\w+)\s*\(/);
            if (funcMatch) {
              const funcName = funcMatch[1];
              const args = Object.values(tc.input)
                .map(v => JSON.stringify(v))
                .join(', ');
              
              const actualResult = await pyodideRef.current.runPythonAsync(`
import json
result = ${funcName}(${args})
json.dumps(result)
              `);
              
              const actual = JSON.parse(String(actualResult));
              testResults.push({
                name: tc.name || `Test ${i + 1}`,
                passed: JSON.stringify(actual) === JSON.stringify(tc.expected),
                expected: JSON.stringify(tc.expected),
                actual: JSON.stringify(actual),
              });
            }
          } catch (err) {
            testResults.push({
              name: tc.name || `Test ${i + 1}`,
              passed: false,
              expected: JSON.stringify(tc.expected),
              actual: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
            });
          }
        }
      }

      return {
        output: String(output),
        error: null,
        executionTime,
        testResults,
      };
    } catch (err) {
      return {
        output: '',
        error: err instanceof Error ? err.message : 'Python execution error',
        executionTime: performance.now() - startTime,
      };
    }
  };

  const executeCode = async (
    code: string,
    language: string,
    testCases?: TestCase[]
  ): Promise<CodeExecutionResult> => {
    setIsExecuting(true);

    try {
      let executionResult: CodeExecutionResult;

      switch (language.toLowerCase()) {
        case 'javascript':
        case 'js':
          executionResult = await executeJavaScript(code, testCases);
          break;
        case 'python':
        case 'py':
          executionResult = await executePython(code, testCases);
          break;
        default:
          executionResult = {
            output: '',
            error: `Language '${language}' is not supported for execution`,
            executionTime: 0,
          };
      }

      setResult(executionResult);
      return executionResult;
    } finally {
      setIsExecuting(false);
    }
  };

  return {
    isExecuting,
    result,
    pyodideLoaded,
    executeCode,
    loadPyodide,
  };
}

// ==========================================
// 3. 实时写作反馈 Hook
// ==========================================
export interface WritingFeedback {
  type: 'grammar' | 'style' | 'suggestion';
  message: string;
  start: number;
  end: number;
  replacement?: string;
}

export interface WritingAnalysis {
  wordCount: number;
  sentenceCount: number;
  paragraphCount: number;
  avgSentenceLength: number;
  readabilityScore: number;
  feedback: WritingFeedback[];
}

export function useWritingAnalyzer() {
  const [analysis, setAnalysis] = useState<WritingAnalysis | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // 基本语法检查规则
  const grammarRules = [
    { pattern: /\bi\s/gi, message: "大写 'I'", replacement: 'I ' },
    { pattern: /\s{2,}/g, message: '多余空格', replacement: ' ' },
    { pattern: /[.!?]\s*[a-z]/g, message: '句首应大写' },
    { pattern: /,\s*,/g, message: '重复逗号' },
    { pattern: /\b(teh|hte|taht|adn|fo)\b/gi, message: '常见拼写错误' },
    { pattern: /[.!?][.!?]+/g, message: '多余标点' },
  ];

  // 分析文本
  const analyzeText = useCallback((text: string): WritingAnalysis => {
    const words = text.trim().split(/\s+/).filter(w => w.length > 0);
    const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 0);
    const paragraphs = text.split(/\n\n+/).filter(p => p.trim().length > 0);

    const wordCount = words.length;
    const sentenceCount = sentences.length;
    const paragraphCount = paragraphs.length;
    const avgSentenceLength = sentenceCount > 0 ? wordCount / sentenceCount : 0;

    // 简单的可读性评分 (Flesch-Kincaid近似)
    const syllables = words.reduce((acc, word) => {
      return acc + (word.match(/[aeiouy]+/gi)?.length || 1);
    }, 0);
    const avgSyllablesPerWord = wordCount > 0 ? syllables / wordCount : 0;
    const readabilityScore = Math.max(0, Math.min(100,
      206.835 - 1.015 * avgSentenceLength - 84.6 * avgSyllablesPerWord
    ));

    // 收集反馈
    const feedback: WritingFeedback[] = [];

    // 检查语法规则
    grammarRules.forEach(rule => {
      let match;
      const regex = new RegExp(rule.pattern.source, rule.pattern.flags);
      while ((match = regex.exec(text)) !== null) {
        feedback.push({
          type: 'grammar',
          message: rule.message,
          start: match.index,
          end: match.index + match[0].length,
          replacement: rule.replacement,
        });
      }
    });

    // 风格建议
    if (avgSentenceLength > 25) {
      feedback.push({
        type: 'style',
        message: '句子偏长，考虑拆分以提高可读性',
        start: 0,
        end: 0,
      });
    }

    if (paragraphCount === 1 && sentenceCount > 5) {
      feedback.push({
        type: 'suggestion',
        message: '建议分段以改善文章结构',
        start: 0,
        end: 0,
      });
    }

    return {
      wordCount,
      sentenceCount,
      paragraphCount,
      avgSentenceLength: Math.round(avgSentenceLength * 10) / 10,
      readabilityScore: Math.round(readabilityScore),
      feedback,
    };
  }, []);

  // 防抖分析
  const debouncedAnalyze = useCallback((text: string) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    setIsAnalyzing(true);

    debounceRef.current = setTimeout(() => {
      const result = analyzeText(text);
      setAnalysis(result);
      setIsAnalyzing(false);
    }, 300);
  }, [analyzeText]);

  return {
    analysis,
    isAnalyzing,
    analyzeText: debouncedAnalyze,
  };
}

// ==========================================
// 4. 键盘活动追踪 Hook (防抄袭)
// ==========================================
export interface KeystrokeData {
  totalKeystrokes: number;
  charsPerMinute: number;
  pasteCount: number;
  deleteCount: number;
  typingPatterns: number[];
  suspiciousActivity: boolean;
}

export function useKeystrokeTracker() {
  const [keystrokeData, setKeystrokeData] = useState<KeystrokeData>({
    totalKeystrokes: 0,
    charsPerMinute: 0,
    pasteCount: 0,
    deleteCount: 0,
    typingPatterns: [],
    suspiciousActivity: false,
  });

  const startTimeRef = useRef<number>(Date.now());
  const keystrokesRef = useRef<number>(0);
  const pasteCountRef = useRef<number>(0);
  const deleteCountRef = useRef<number>(0);
  const lastKeystrokeTimeRef = useRef<number>(Date.now());
  const intervalGapsRef = useRef<number[]>([]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const now = Date.now();
    const gap = now - lastKeystrokeTimeRef.current;
    lastKeystrokeTimeRef.current = now;

    // 记录击键间隔
    if (gap < 5000) {
      intervalGapsRef.current.push(gap);
      // 只保留最近100个间隔
      if (intervalGapsRef.current.length > 100) {
        intervalGapsRef.current.shift();
      }
    }

    keystrokesRef.current++;

    if (e.key === 'Backspace' || e.key === 'Delete') {
      deleteCountRef.current++;
    }

    // 更新状态
    const elapsedMinutes = (now - startTimeRef.current) / 60000;
    const charsPerMinute = elapsedMinutes > 0 
      ? Math.round(keystrokesRef.current / elapsedMinutes) 
      : 0;

    // 检测可疑活动（打字速度异常快）
    const suspiciousActivity = charsPerMinute > 500 || pasteCountRef.current > 5;

    setKeystrokeData({
      totalKeystrokes: keystrokesRef.current,
      charsPerMinute,
      pasteCount: pasteCountRef.current,
      deleteCount: deleteCountRef.current,
      typingPatterns: [...intervalGapsRef.current],
      suspiciousActivity,
    });
  }, []);

  const handlePaste = useCallback(() => {
    pasteCountRef.current++;
    setKeystrokeData(prev => ({
      ...prev,
      pasteCount: pasteCountRef.current,
      suspiciousActivity: pasteCountRef.current > 5,
    }));
  }, []);

  const reset = useCallback(() => {
    startTimeRef.current = Date.now();
    keystrokesRef.current = 0;
    pasteCountRef.current = 0;
    deleteCountRef.current = 0;
    lastKeystrokeTimeRef.current = Date.now();
    intervalGapsRef.current = [];
    setKeystrokeData({
      totalKeystrokes: 0,
      charsPerMinute: 0,
      pasteCount: 0,
      deleteCount: 0,
      typingPatterns: [],
      suspiciousActivity: false,
    });
  }, []);

  return {
    keystrokeData,
    handleKeyDown,
    handlePaste,
    reset,
  };
}

// ==========================================
// 5. 本地存储 Hook
// ==========================================
export function useLocalStorage<T>(key: string, initialValue: T) {
  const [storedValue, setStoredValue] = useState<T>(initialValue);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    try {
      const item = localStorage.getItem(key);
      if (item) {
        setStoredValue(JSON.parse(item));
      }
    } catch (error) {
      logger.error('Error reading from localStorage', error);
    }
    setIsLoaded(true);
  }, [key]);

  const setValue = useCallback((value: T | ((val: T) => T)) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);
      localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      logger.error('Error writing to localStorage', error);
    }
  }, [key, storedValue]);

  return [storedValue, setValue, isLoaded] as const;
}

// ==========================================
// 6. Whisper 语音转录 Hook
// ==========================================
export interface TranscriptionResult {
  text: string;
  confidence: number;
  duration: number;
  language?: string;
}

export interface WhisperTranscriberState {
  isTranscribing: boolean;
  result: TranscriptionResult | null;
  error: string | null;
}

export function useWhisperTranscriber() {
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const transcribeAudio = useCallback(async (audioBlob: Blob): Promise<TranscriptionResult | null> => {
    setIsTranscribing(true);
    setError(null);

    try {
      // 创建 FormData 发送音频文件
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

      const headers: Record<string, string> = {};
      const token = getToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}/ai/transcribe`, {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Transcription failed: ${response.statusText}`);
      }

      const data = await response.json();
      
      const transcriptionResult: TranscriptionResult = {
        text: data.text || '',
        confidence: data.confidence || 0.9,
        duration: data.duration || 0,
        language: data.language || 'zh',
      };

      setResult(transcriptionResult);
      return transcriptionResult;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Transcription failed';
      setError(message);
      logger.error('Whisper transcription error', err);
      return null;
    } finally {
      setIsTranscribing(false);
    }
  }, []);

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return {
    isTranscribing,
    result,
    error,
    transcribeAudio,
    reset,
  };
}

// ==========================================
// 7. AI 写作反馈 Hook (实时)
// ==========================================
export interface AIWritingFeedback {
  grammar: { score: number; issues: { text: string; suggestion: string; position: number }[] };
  content: { score: number; suggestions: string[] };
  structure: { score: number; feedback: string };
  style: { score: number; tone: string; suggestions: string[] };
  overall: number;
}

export function useAIWritingFeedback() {
  const [feedback, setFeedback] = useState<AIWritingFeedback | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const analyzeWriting = useCallback(async (text: string, prompt?: string) => {
    if (text.length < 50) {
      setFeedback(null);
      return;
    }

    // Debounce API calls
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(async () => {
      if (!mountedRef.current) return;
      setIsAnalyzing(true);
      try {
        const response = await fetch(`${API_BASE_URL}/ai/analyze-writing`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, prompt }),
        });

        if (!response.ok) {
          throw new Error('Analysis failed');
        }

        const data = await response.json();
        if (mountedRef.current) setFeedback(data);
      } catch (err) {
        logger.error('AI writing analysis error', err);
        if (mountedRef.current) setFeedback(generateLocalFeedback(text));
      } finally {
        if (mountedRef.current) setIsAnalyzing(false);
      }
    }, 1500);
  }, []);

  return {
    feedback,
    isAnalyzing,
    analyzeWriting,
  };
}

// 本地反馈生成（当 AI 不可用时）
function generateLocalFeedback(text: string): AIWritingFeedback {
  const words = text.split(/\s+/).filter(w => w.length > 0);
  const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 0);
  const avgSentenceLength = words.length / Math.max(sentences.length, 1);
  
  const grammarIssues: { text: string; suggestion: string; position: number }[] = [];
  
  // 检测常见问题
  const doubleSpaces = text.match(/\s{2,}/g);
  if (doubleSpaces) {
    grammarIssues.push({ text: '多余空格', suggestion: '删除重复空格', position: text.indexOf('  ') });
  }
  
  const grammarScore = Math.max(60, 100 - grammarIssues.length * 10);
  const contentScore = Math.min(100, 50 + words.length / 5);
  const structureScore = sentences.length >= 3 ? 80 : 60;
  const styleScore = avgSentenceLength > 25 ? 65 : 85;

  return {
    grammar: { score: grammarScore, issues: grammarIssues },
    content: { 
      score: contentScore, 
      suggestions: words.length < 100 ? ['建议增加更多内容以充分论述观点'] : [] 
    },
    structure: { 
      score: structureScore, 
      feedback: sentences.length < 3 ? '建议分成多个段落' : '段落结构合理' 
    },
    style: { 
      score: styleScore, 
      tone: '正式',
      suggestions: avgSentenceLength > 25 ? ['部分句子偏长，考虑拆分'] : []
    },
    overall: Math.round((grammarScore + contentScore + structureScore + styleScore) / 4),
  };
}

// ==========================================
// 8. 成就系统 Hook
// ==========================================
export interface Achievement {
  id: string;
  name: string;
  nameEn: string;
  nameZhTW: string;
  description: string;
  descriptionEn: string;
  descriptionZhTW: string;
  icon: string;
  category: 'assessment' | 'learning' | 'milestone' | 'special';
  progress: number;
  target: number;
  unlocked: boolean;
  unlockedAt?: string;
  rarity: 'common' | 'rare' | 'epic' | 'legendary';
}

export interface AchievementState {
  achievements: Achievement[];
  totalPoints: number;
  recentUnlock: Achievement | null;
}

const DEFAULT_ACHIEVEMENTS: Achievement[] = [
  // 评估成就
  { id: 'first_assessment', name: '初次尝试', nameEn: 'First Try', nameZhTW: '初次嘗試', description: '完成第一次评估', descriptionEn: 'Complete your first assessment', descriptionZhTW: '完成第一次評估', icon: '🎯', category: 'assessment', progress: 0, target: 1, unlocked: false, rarity: 'common' },
  { id: 'comm_master', name: '沟通达人', nameEn: 'Communication Master', nameZhTW: '溝通達人', description: '沟通能力评估获得80分以上', descriptionEn: 'Score 80+ on communication assessment', descriptionZhTW: '溝通能力評估獲得80分以上', icon: '🎙️', category: 'assessment', progress: 0, target: 80, unlocked: false, rarity: 'rare' },
  { id: 'code_ninja', name: '代码忍者', nameEn: 'Code Ninja', nameZhTW: '代碼忍者', description: '编程评估获得90分以上', descriptionEn: 'Score 90+ on programming assessment', descriptionZhTW: '編程評估獲得90分以上', icon: '💻', category: 'assessment', progress: 0, target: 90, unlocked: false, rarity: 'epic' },
  { id: 'writer', name: '文字工匠', nameEn: 'Word Smith', nameZhTW: '文字工匠', description: '写作评估获得85分以上', descriptionEn: 'Score 85+ on writing assessment', descriptionZhTW: '寫作評估獲得85分以上', icon: '✍️', category: 'assessment', progress: 0, target: 85, unlocked: false, rarity: 'rare' },
  { id: 'triple_threat', name: '三栖能手', nameEn: 'Triple Threat', nameZhTW: '三棲能手', description: '三项评估均达到75分以上', descriptionEn: 'Score 75+ on all three assessments', descriptionZhTW: '三項評估均達到75分以上', icon: '🏆', category: 'assessment', progress: 0, target: 3, unlocked: false, rarity: 'legendary' },

  // 学习成就
  { id: 'skill_seeker', name: '技能探索者', nameEn: 'Skill Seeker', nameZhTW: '技能探索者', description: '解锁5项技能', descriptionEn: 'Unlock 5 skills', descriptionZhTW: '解鎖5項技能', icon: '🔍', category: 'learning', progress: 0, target: 5, unlocked: false, rarity: 'common' },
  { id: 'document_master', name: '文档达人', nameEn: 'Document Master', nameZhTW: '文件達人', description: '上传10份证据文档', descriptionEn: 'Upload 10 evidence documents', descriptionZhTW: '上傳10份證據文件', icon: '📚', category: 'learning', progress: 0, target: 10, unlocked: false, rarity: 'rare' },

  // 里程碑
  { id: 'week_streak', name: '持续进步', nameEn: 'On a Roll', nameZhTW: '持續進步', description: '连续7天登录', descriptionEn: '7-day login streak', descriptionZhTW: '連續7天登錄', icon: '🔥', category: 'milestone', progress: 0, target: 7, unlocked: false, rarity: 'rare' },
  { id: 'perfectionist', name: '完美主义者', nameEn: 'Perfectionist', nameZhTW: '完美主義者', description: '任意评估获得100分', descriptionEn: 'Score 100 on any assessment', descriptionZhTW: '任意評估獲得100分', icon: '💯', category: 'milestone', progress: 0, target: 100, unlocked: false, rarity: 'legendary' },

  // 特殊成就
  { id: 'early_bird', name: '早起鸟', nameEn: 'Early Bird', nameZhTW: '早起鳥', description: '在早上6点前完成评估', descriptionEn: 'Complete assessment before 6 AM', descriptionZhTW: '在早上6點前完成評估', icon: '🌅', category: 'special', progress: 0, target: 1, unlocked: false, rarity: 'epic' },
  { id: 'night_owl', name: '夜猫子', nameEn: 'Night Owl', nameZhTW: '夜貓子', description: '在凌晨12点后完成评估', descriptionEn: 'Complete assessment after midnight', descriptionZhTW: '在凌晨12點後完成評估', icon: '🦉', category: 'special', progress: 0, target: 1, unlocked: false, rarity: 'epic' },

  // 社交分享成就 (P3)
  { id: 'share_master', name: '分享达人', nameEn: 'Share Master', nameZhTW: '分享達人', description: '分享技能档案给朋友', descriptionEn: 'Share your skills profile with others', descriptionZhTW: '分享技能檔案給朋友', icon: '📤', category: 'special', progress: 0, target: 1, unlocked: false, rarity: 'rare' },
];

export function useAchievements() {
  const [achievements, setAchievements] = useState<Achievement[]>(DEFAULT_ACHIEVEMENTS);
  const [recentUnlock, setRecentUnlock] = useState<Achievement | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { studentBff } = await import('@/lib/bffClient');
        const data = await studentBff.getAchievements();
        if (cancelled) return;
        const list = (data.achievements || []) as Achievement[];
        if (list.length > 0) {
          setAchievements(list.map(a => ({
            ...a,
            unlockedAt: a.unlockedAt ?? (a as unknown as Record<string, unknown>).unlocked_at as string | undefined,
          })));
        }
        if (data.recentUnlock) setRecentUnlock(data.recentUnlock as Achievement);
      } catch (e) {
        logger.error('Failed to load achievements', e);
        try {
          const saved = localStorage.getItem('skillsight-achievements');
          if (saved) {
            try {
              const parsed = JSON.parse(saved);
              setAchievements(prev => prev.map(a => {
                const savedA = parsed.find((s: Achievement) => s.id === a.id);
                return savedA ? { ...a, ...savedA } : a;
              }));
            } catch {
              // ignore
            }
          }
        } catch (e) {
          logger.warn('Failed to read achievements from localStorage', e);
        }
      } finally {
        if (!cancelled) setLoaded(true);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  const updateProgress = useCallback((achievementId: string, progress: number) => {
    setAchievements(prev => {
      const updated = prev.map(a => {
        if (a.id !== achievementId) return a;
        const newProgress = Math.min(progress, a.target);
        const wasUnlocked = a.unlocked;
        const isNowUnlocked = newProgress >= a.target;
        if (!wasUnlocked && isNowUnlocked) {
          const unlockedAchievement = { ...a, progress: newProgress, unlocked: true, unlockedAt: new Date().toISOString() };
          setRecentUnlock(unlockedAchievement);
          return unlockedAchievement;
        }
        return { ...a, progress: newProgress };
      });
      try {
        localStorage.setItem('skillsight-achievements', JSON.stringify(updated));
      } catch (e) {
        logger.warn('Failed to save achievements to localStorage', e);
      }
      import('@/lib/bffClient').then(({ studentBff }) => {
        studentBff.postAchievementProgress(achievementId, progress).catch(() => {});
      });
      return updated;
    });
  }, []);

  const checkAssessmentAchievements = useCallback((type: 'communication' | 'programming' | 'writing' | 'data_analysis' | 'problem_solving' | 'presentation', score: number) => {
    // 首次评估
    updateProgress('first_assessment', 1);
    
    // 类型相关成就
    if (type === 'communication' && score >= 80) {
      updateProgress('comm_master', score);
    }
    if (type === 'programming' && score >= 90) {
      updateProgress('code_ninja', score);
    }
    if (type === 'writing' && score >= 85) {
      updateProgress('writer', score);
    }
    
    // 满分成就
    if (score === 100) {
      updateProgress('perfectionist', 100);
    }
    
    // 时间相关成就
    const hour = new Date().getHours();
    if (hour < 6) {
      updateProgress('early_bird', 1);
    }
    if (hour >= 0 && hour < 4) {
      updateProgress('night_owl', 1);
    }
  }, [updateProgress]);

  const dismissRecentUnlock = useCallback(() => {
    setRecentUnlock(null);
  }, []);

  // Unlock share_master achievement (called after successful share)
  const unlockShareAchievement = useCallback(() => {
    setAchievements(prev => {
      const exists = prev.find(a => a.id === 'share_master');
      if (!exists || exists.unlocked) return prev;

      const updated = prev.map(a =>
        a.id === 'share_master'
          ? { ...a, unlocked: true, unlockedAt: new Date().toISOString(), progress: 1 }
          : a
      );

      // Show notification
      const achievement = updated.find(a => a.id === 'share_master');
      if (achievement) {
        setRecentUnlock(achievement);
      }

      // Persist to localStorage
      try {
        localStorage.setItem('skillsight-achievements', JSON.stringify(updated));
      } catch {}

      return updated;
    });
  }, []);

  const totalPoints = achievements.filter(a => a.unlocked).reduce((sum, a) => {
    const points = { common: 10, rare: 25, epic: 50, legendary: 100 };
    return sum + points[a.rarity];
  }, 0);

  return {
    achievements,
    totalPoints,
    recentUnlock,
    updateProgress,
    checkAssessmentAchievements,
    dismissRecentUnlock,
    unlockShareAchievement,
  };
}

// ==========================================
// 9. 学习路径推荐 Hook
// ==========================================
export interface LearningRecommendation {
  id: string;
  title: string;
  titleEn: string;
  description: string;
  descriptionEn: string;
  type: 'course' | 'project' | 'assessment' | 'resource';
  skill: string;
  priority: 'high' | 'medium' | 'low';
  estimatedHours: number;
  url?: string;
  icon: string;
  progress?: number;
}

export interface SkillGap {
  skill: string;
  currentLevel: number;
  targetLevel: number;
  gap: number;
}

export function useLearningPath() {
  const [recommendations, setRecommendations] = useState<LearningRecommendation[]>([]);
  const [skillGaps, setSkillGaps] = useState<SkillGap[]>([]);
  const [loading, setLoading] = useState(false);

  const generateRecommendations = useCallback(async (
    skills: { name: string; level: number }[],
    _targetRole?: string
  ) => {
    if (!skills || skills.length === 0) {
      setLoading(false);
      return;
    }

    setLoading(true);

    try {
      const gaps: SkillGap[] = skills
        .filter(s => s.level < 3)
        .map(s => ({
          skill: s.name,
          currentLevel: s.level,
          targetLevel: 3,
          gap: 3 - s.level,
        }))
        .sort((a, b) => b.gap - a.gap);

      setSkillGaps(gaps);

      const token = typeof window !== 'undefined' ? localStorage.getItem('skillsight_token') : null;
      let courseRecs: LearningRecommendation[] = [];

      if (token) {
        try {
          const res = await fetch(
            `${API_BASE_URL}/bff/student/courses/for-gaps`,
            {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({ skill_ids: gaps.map(g => g.skill).length > 0 ? undefined : undefined }),
            }
          );
          if (res.ok) {
            const data = await res.json();
            const courses = (data.items || []) as Array<{
              course_id: string;
              course_name: string;
              credits: number;
              programme: string;
              skills: Array<{ skill_id: string; skill_name: string }>;
            }>;
            courseRecs = courses.slice(0, 8).map((c, i) => ({
              id: `course-${c.course_id}`,
              title: `${c.course_id} — ${c.course_name}`,
              titleEn: `${c.course_id} — ${c.course_name}`,
              description: `${c.programme} · ${c.credits} credits · Develops: ${c.skills.map(s => s.skill_name).join(', ')}`,
              descriptionEn: `${c.programme} · ${c.credits} credits · Develops: ${c.skills.map(s => s.skill_name).join(', ')}`,
              type: 'course' as const,
              skill: c.skills[0]?.skill_name || '',
              priority: i < 3 ? 'high' as const : i < 6 ? 'medium' as const : 'low' as const,
              estimatedHours: c.credits * 4,
              icon: '📚',
            }));
          }
        } catch {
          // fall through to local recs
        }
      }

      if (courseRecs.length > 0) {
        setRecommendations(courseRecs);
      } else {
        const localRecs: LearningRecommendation[] = gaps.slice(0, 5).map((gap, i) => ({
          id: `rec-${i}`,
          title: `Improve ${gap.skill}`,
          titleEn: `Improve ${gap.skill}`,
          description: `Practice and projects to improve your ${gap.skill} skills`,
          descriptionEn: `Practice and projects to improve your ${gap.skill} skills`,
          type: i % 2 === 0 ? 'course' as const : 'project' as const,
          skill: gap.skill,
          priority: gap.gap >= 2 ? 'high' as const : gap.gap === 1 ? 'medium' as const : 'low' as const,
          estimatedHours: gap.gap * 10,
          icon: i % 3 === 0 ? '📚' : i % 3 === 1 ? '💻' : '📝',
        }));
        setRecommendations(localRecs);
      }
    } catch (err) {
      logger.error('Failed to generate learning path', err);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    recommendations,
    skillGaps,
    loading,
    generateRecommendations,
  };
}
