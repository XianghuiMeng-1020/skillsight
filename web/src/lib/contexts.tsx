'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { usePathname } from 'next/navigation';

// ==========================================
// 1. 主题上下文 (深色模式)
// ==========================================
type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('light');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const savedTheme = localStorage.getItem('skillsight-theme') as Theme;
    if (savedTheme) {
      setThemeState(savedTheme);
      document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setThemeState('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  }, []);

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem('skillsight-theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  }, [theme, setTheme]);

  // Always provide context so useTheme() never throws (SSR-safe when !mounted)
  const value = mounted
    ? { theme, toggleTheme, setTheme }
    : { theme: 'light' as Theme, toggleTheme: () => {}, setTheme: () => {} };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

const defaultThemeContext: ThemeContextType = {
  theme: 'light',
  toggleTheme: () => {},
  setTheme: () => {},
};

export function useTheme() {
  const context = useContext(ThemeContext);
  return context ?? defaultThemeContext;
}

// ==========================================
// 2. 语言上下文 (多语言支持)
// ==========================================
export type Language = 'zh' | 'zh-TW' | 'en';

export const LANGUAGES: { value: Language; label: string; short: string }[] = [
  { value: 'zh', label: '简体中文', short: '简' },
  { value: 'zh-TW', label: '繁體中文', short: '繁' },
  { value: 'en', label: 'English', short: 'EN' },
];

interface Translations {
  [key: string]: {
    zh: string;
    'zh-TW': string;
    en: string;
  };
}

// 完整的翻译字典
export const translations: Translations = {
  // 导航
  'nav.home': { zh: '首页', 'zh-TW': '首頁', en: 'Home' },
  'nav.upload': { zh: '上传', 'zh-TW': '上傳', en: 'Upload' },
  'nav.assess': { zh: '评估', 'zh-TW': '評估', en: 'Assess' },
  'nav.dashboard': { zh: '技能档案', 'zh-TW': '技能檔案', en: 'Dashboard' },
  'nav.settings': { zh: '设置', 'zh-TW': '設定', en: 'Settings' },
  'nav.privacy': { zh: '隐私与数据', 'zh-TW': '隱私與資料', en: 'Privacy & Data' },
  'nav.mainMenu': { zh: '主导航', 'zh-TW': '主選單', en: 'Main Menu' },
  'nav.openMenu': { zh: '打开菜单', 'zh-TW': '開啟選單', en: 'Open menu' },
  'nav.closeMenu': { zh: '关闭菜单', 'zh-TW': '關閉選單', en: 'Close menu' },
  'admin.administration': { zh: '管理', 'zh-TW': '管理', en: 'Administration' },
  'admin.overview': { zh: '概览', 'zh-TW': '概覽', en: 'Overview' },
  'admin.students': { zh: '学生', 'zh-TW': '學生', en: 'Students' },
  'admin.reviewQueue': { zh: '审核队列', 'zh-TW': '審核佇列', en: 'Review Queue' },
  'admin.skillsRegistry': { zh: '技能注册', 'zh-TW': '技能註冊', en: 'Skills Registry' },
  'admin.rolesLibrary': { zh: '角色库', 'zh-TW': '角色庫', en: 'Roles Library' },
  'admin.courses': { zh: '课程', 'zh-TW': '課程', en: 'Courses' },
  'admin.analytics': { zh: '分析', 'zh-TW': '分析', en: 'Analytics' },
  'user.administrator': { zh: '管理员', 'zh-TW': '管理員', en: 'Administrator' },
  'user.student': { zh: '学生', 'zh-TW': '學生', en: 'Student' },
  'action.signOut': { zh: '退出登录', 'zh-TW': '登出', en: 'Sign out' },

  // Dashboard
  'dashboard.welcome': { zh: '欢迎回来', 'zh-TW': '歡迎回來', en: 'Welcome back' },
  'dashboard.skills': { zh: '我的技能', 'zh-TW': '我的技能', en: 'My Skills' },
  'dashboard.documents': { zh: '最近上传', 'zh-TW': '最近上傳', en: 'Recent Uploads' },
  'dashboard.jobs': { zh: '职位匹配', 'zh-TW': '職位匹配', en: 'Job Matching' },
  'dashboard.assessments': { zh: '评估', 'zh-TW': '評估', en: 'Assessments' },
  'dashboard.uploadEvidence': { zh: '上传证据', 'zh-TW': '上傳證據', en: 'Upload Evidence' },
  'dashboard.takeAssessment': { zh: '参加评估', 'zh-TW': '參加評估', en: 'Take Assessment' },
  'dashboard.findJobs': { zh: '寻找职位', 'zh-TW': '尋找職位', en: 'Find Jobs' },
  'dashboard.skillsVerified': { zh: '已验证技能', 'zh-TW': '已驗證技能', en: 'Skills Verified' },
  'dashboard.inProgress': { zh: '进行中', 'zh-TW': '進行中', en: 'In Progress' },
  'dashboard.jobsMatched': { zh: '匹配职位', 'zh-TW': '匹配職位', en: 'Jobs Matched' },
  'dashboard.docsUploaded': { zh: '已上传文档', 'zh-TW': '已上傳文件', en: 'Documents Uploaded' },
  'dashboard.recommendations': { zh: '推荐下一步', 'zh-TW': '推薦下一步', en: 'Recommended Next Steps' },
  'dashboard.viewAll': { zh: '查看全部', 'zh-TW': '查看全部', en: 'View all' },
  'dashboard.refresh': { zh: '刷新列表', 'zh-TW': '重新整理列表', en: 'Refresh list' },
  'dashboard.statDocsTip': { zh: '你已上传并授权用于评估的证据文档数量', 'zh-TW': '你已上傳並授權用於評估的證據文件數量', en: 'Total evidence documents you have uploaded and authorized' },
  'dashboard.statVerifiedTip': { zh: '当前已达到较高可信度的技能数量', 'zh-TW': '目前已達到較高可信度的技能數量', en: 'Skills currently assessed with higher confidence' },
  'dashboard.statProgressTip': { zh: '正在处理中或证据仍不足的技能数量', 'zh-TW': '正在處理中或證據仍不足的技能數量', en: 'Skills in progress or still lacking evidence' },
  'dashboard.statJobsTip': { zh: '系统基于你的技能档案计算出的匹配职位数量', 'zh-TW': '系統基於你的技能檔案計算出的匹配職位數量', en: 'Number of role matches computed from your skill profile' },
  'dashboard.actionUploadTip': { zh: '先上传项目、报告、代码或作品，系统会自动提取证据', 'zh-TW': '先上傳專案、報告、程式碼或作品，系統會自動提取證據', en: 'Upload projects, reports, code, or portfolios to extract evidence' },
  'dashboard.actionAssessTip': { zh: '通过互动评估补充沟通、编程、写作能力证据', 'zh-TW': '透過互動評估補充溝通、程式設計、寫作能力證據', en: 'Use interactive assessments to add communication/coding/writing evidence' },
  'dashboard.actionJobsTip': { zh: '查看你与目标岗位的差距，并获得改进建议', 'zh-TW': '查看你與目標職位的差距，並獲得改進建議', en: 'See readiness gaps against target roles and get next-step suggestions' },
  'dashboard.firstTimeHint': { zh: '新手路线：先上传证据，再做评估，最后查看技能档案与职位匹配。', 'zh-TW': '新手路線：先上傳證據，再做評估，最後查看技能檔案與職位匹配。', en: 'Starter route: upload evidence, complete an assessment, then check skills and job matches.' },

  // 评估页面
  'assess.title': { zh: '交互式能力评估', 'zh-TW': '互動式能力評估', en: 'Interactive Assessment' },
  'assess.subtitle': { zh: '通过实时评估验证你的沟通、编程和写作能力', 'zh-TW': '透過即時評估驗證你的溝通、程式設計和寫作能力', en: 'Verify your communication, programming, and writing skills through real-time assessment' },
  'assess.communication': { zh: '沟通能力', 'zh-TW': '溝通能力', en: 'Communication' },
  'assess.programming': { zh: '编程能力', 'zh-TW': '程式設計能力', en: 'Programming' },
  'assess.writing': { zh: '写作能力', 'zh-TW': '寫作能力', en: 'Writing' },
  'assess.videoStyle': { zh: '视频面试风格', 'zh-TW': '影片面試風格', en: 'Video Interview Style' },
  'assess.leetcodeStyle': { zh: 'LeetCode 风格', 'zh-TW': 'LeetCode 風格', en: 'LeetCode Style' },
  'assess.timedWriting': { zh: '限时写作', 'zh-TW': '限時寫作', en: 'Timed Writing' },
  'assess.start': { zh: '开始评估', 'zh-TW': '開始評估', en: 'Start Assessment' },
  'assess.submit': { zh: '提交', 'zh-TW': '提交', en: 'Submit' },
  'assess.result': { zh: '评估结果', 'zh-TW': '評估結果', en: 'Assessment Result' },
  'assess.lines': { zh: '行', 'zh-TW': '行', en: 'lines' },
  'assess.running': { zh: '运行中...', 'zh-TW': '執行中...', en: 'Running...' },
  'assess.runTests': { zh: '运行测试', 'zh-TW': '執行測試', en: 'Run Tests' },
  'assess.runTimeout': { zh: '运行超时，请稍后重试', 'zh-TW': '執行逾時，請稍後重試', en: 'Run timed out, please try again' },
  'assess.writingInstructions': { zh: '系统将给你一个写作主题，你需要在 30 分钟内完成 300-500 字的文章。系统会检测复制粘贴行为，请手动输入。', 'zh-TW': '系統將給你一個寫作主題，你需要在 30 分鐘內完成 300-500 字的文章。系統會檢測複製貼上行為，請手動輸入。', en: 'You will receive a writing topic and have 30 minutes to compose a 300-500 word essay. Copy-paste is detected; please type manually.' },
  'assess.programmingTitle': { zh: '编程能力评估', 'zh-TW': '程式設計能力評估', en: 'Programming Assessment' },
  'assess.programmingDesc': { zh: '选择难度等级，系统将生成一道算法题目。', 'zh-TW': '選擇難度等級，系統將生成一道演算法題目。', en: 'Choose a difficulty level and the system will generate an algorithm problem.' },
  'assess.writingTitle': { zh: '写作能力评估', 'zh-TW': '寫作能力評估', en: 'Writing Assessment' },
  'assess.minutes': { zh: '分钟', 'zh-TW': '分鐘', en: 'min' },
  'assess.words': { zh: '字', 'zh-TW': '字', en: 'words' },
  'assess.antiPlagiarism': { zh: '防抄袭', 'zh-TW': '防抄襲', en: 'Anti-plagiarism' },
  'assess.preparing': { zh: '准备中...', 'zh-TW': '準備中...', en: 'Preparing...' },
  'assess.yourTopic': { zh: '你的话题', 'zh-TW': '你的話題', en: 'Your Topic' },
  'assess.transcribing': { zh: '转录中...', 'zh-TW': '轉錄中...', en: 'Transcribing...' },
  'assess.seconds': { zh: '秒', 'zh-TW': '秒', en: 's' },
  'assess.transcriptionResult': { zh: '转录结果', 'zh-TW': '轉錄結果', en: 'Transcription Result' },
  'assess.submitting': { zh: '提交中...', 'zh-TW': '提交中...', en: 'Submitting...' },
  'assess.submitAssessment': { zh: '提交评估', 'zh-TW': '提交評估', en: 'Submit Assessment' },
  'assess.output': { zh: '输出', 'zh-TW': '輸出', en: 'Output' },
  'assess.traditionalMode': { zh: '传统评估', 'zh-TW': '傳統評估', en: 'Traditional Assessment' },
  'assess.aiAgentMode': { zh: '与 AI Agent 评估', 'zh-TW': '與 AI Agent 評估', en: 'Take assessment with our AI Agent' },
  'assess.testResults': { zh: '测试结果', 'zh-TW': '測試結果', en: 'Test Results' },
  'assess.expected': { zh: '期望', 'zh-TW': '期望', en: 'Expected' },
  'assess.actual': { zh: '实际', 'zh-TW': '實際', en: 'Actual' },
  'assess.evaluating': { zh: '评估中...', 'zh-TW': '評估中...', en: 'Evaluating...' },
  'assess.aiRealtimeFeedback': { zh: 'AI 实时反馈', 'zh-TW': 'AI 即時回饋', en: 'AI Real-time Feedback' },
  'assess.style': { zh: '风格', 'zh-TW': '風格', en: 'Style' },
  'assess.suggestions': { zh: '建议', 'zh-TW': '建議', en: 'Suggestions' },
  'assess.grammarIssues': { zh: '语法问题', 'zh-TW': '語法問題', en: 'Grammar Issues' },
  'assess.aiAnalysisHint': { zh: '开始写作后，AI 将实时分析你的文章并提供反馈', 'zh-TW': '開始寫作後，AI 將即時分析你的文章並提供回饋', en: 'After you start writing, AI will analyze your essay and provide feedback in real-time' },
  'assess.codePlaceholder': { zh: '在这里编写你的解答', 'zh-TW': '在這裡編寫你的解答', en: 'Write your solution here' },
  'assess.essayPlaceholder': { zh: '在这里输入你的文章...', 'zh-TW': '在這裡輸入你的文章...', en: 'Type your essay here...' },
  'assess.communicationDesc': { zh: '评估口头表达、逻辑组织、自信度和内容相关性', 'zh-TW': '評估口語表達、邏輯組織、自信度和內容相關性', en: 'Evaluates verbal expression, logical organization, confidence, and content relevance' },
  'assess.programmingAbilityDesc': { zh: '评估代码正确性、效率、风格和问题解决能力', 'zh-TW': '評估程式碼正確性、效率、風格和問題解決能力', en: 'Evaluates code correctness, efficiency, style, and problem-solving ability' },
  'assess.writingAbilityDesc': { zh: '评估语法、结构、内容深度和原创性', 'zh-TW': '評估語法、結構、內容深度和原創性', en: 'Evaluates grammar, structure, content depth, and originality' },
  'assess.retry': { zh: '重新评估', 'zh-TW': '重新評估', en: 'Retry' },
  'assess.recording': { zh: '正在录制中...', 'zh-TW': '正在錄製中...', en: 'Recording...' },
  'assess.startRecording': { zh: '开始录制', 'zh-TW': '開始錄製', en: 'Start Recording' },
  'assess.stopRecording': { zh: '停止录制', 'zh-TW': '停止錄製', en: 'Stop Recording' },
  'assess.submitRecording': { zh: '提交评估', 'zh-TW': '提交評估', en: 'Submit Assessment' },
  'assess.topic': { zh: '你的话题', 'zh-TW': '你的話題', en: 'Your Topic' },
  'assess.difficulty': { zh: '难度', 'zh-TW': '難度', en: 'Difficulty' },
  'assess.easy': { zh: '简单', 'zh-TW': '簡單', en: 'Easy' },
  'assess.medium': { zh: '中等', 'zh-TW': '中等', en: 'Medium' },
  'assess.hard': { zh: '困难', 'zh-TW': '困難', en: 'Hard' },
  'assess.levelBeginner': { zh: '入门', 'zh-TW': '入門', en: 'Beginner' },
  'assess.levelIntermediate': { zh: '进阶', 'zh-TW': '進階', en: 'Intermediate' },
  'assess.levelAdvanced': { zh: '高级', 'zh-TW': '高級', en: 'Advanced' },
  'assess.levelExpert': { zh: '专家', 'zh-TW': '專家', en: 'Expert' },
  'assess.yourCode': { zh: '你的代码', 'zh-TW': '你的程式碼', en: 'Your Code' },
  'assess.submitCode': { zh: '提交代码', 'zh-TW': '提交程式碼', en: 'Submit Code' },
  'assess.writingPrompt': { zh: '写作主题', 'zh-TW': '寫作主題', en: 'Writing Prompt' },
  'assess.submitEssay': { zh: '提交文章', 'zh-TW': '提交文章', en: 'Submit Essay' },
  'assess.wordCount': { zh: '字数', 'zh-TW': '字數', en: 'Word Count' },
  'assess.timeLimit': { zh: '时限', 'zh-TW': '時限', en: 'Time Limit' },
  'assess.aiFeedback': { zh: 'AI 反馈', 'zh-TW': 'AI 回饋', en: 'AI Feedback' },
  'assess.detailedData': { zh: '查看详细数据', 'zh-TW': '查看詳細資料', en: 'View Detailed Data' },
  'assess.instructions': { zh: '评估说明', 'zh-TW': '評估說明', en: 'Assessment Instructions' },
  'assess.history': { zh: '评估历史', 'zh-TW': '評估歷史', en: 'Assessment History' },
  'assess.noHistory': { zh: '暂无评估历史', 'zh-TW': '暫無評估歷史', en: 'No assessment history yet' },
  'assess.noHistoryDesc': { zh: '完成评估后，记录将显示在这里', 'zh-TW': '完成評估後，記錄將顯示在這裡', en: 'Records will appear here after you complete assessments' },
  'assess.assessmentSuffix': { zh: '评估', 'zh-TW': '評估', en: ' Assessment' },
  'assess.startFailed': { zh: '启动失败', 'zh-TW': '啟動失敗', en: 'Start Failed' },
  'assess.startFailedMsg': { zh: '暂时无法开始评估，请稍后再试或联系支持。', 'zh-TW': '暫時無法開始評估，請稍後再試或聯絡支援。', en: 'Assessment could not be started. Please try again later or contact support.' },
  'assess.loginHint': { zh: '登录后可保存评估结果并同步到技能档案。', 'zh-TW': '登入後可儲存評估結果並同步至技能檔案。', en: 'Log in to save results and sync to your skill profile.' },
  'assess.pleaseLogin': { zh: '请先登录', 'zh-TW': '請先登入', en: 'Please log in' },
  'assess.ctaHint': { zh: '选择下方评估类型，点击「开始评估」即可开始', 'zh-TW': '選擇下方評估類型，點擊「開始評估」即可開始', en: 'Choose a type below and click Start Assessment to begin' },
  'assess.transcribeFailed': { zh: '录音转录失败，请重试。', 'zh-TW': '錄音轉錄失敗，請重試。', en: 'Transcription failed, please try again.' },
  'assess.noAudio': { zh: '未检测到录音内容。', 'zh-TW': '未偵測到錄音內容。', en: 'No audio content detected.' },
  'assess.submitFailed': { zh: '提交失败', 'zh-TW': '提交失敗', en: 'Submission Failed' },
  'assess.noOutput': { zh: '无输出', 'zh-TW': '無輸出', en: 'No output' },
  'assess.totalScore': { zh: '总分', 'zh-TW': '總分', en: 'Total Score' },
  'assess.clarity': { zh: '清晰度', 'zh-TW': '清晰度', en: 'Clarity' },
  'assess.content': { zh: '内容', 'zh-TW': '內容', en: 'Content' },
  'assess.confidence': { zh: '自信度', 'zh-TW': '自信度', en: 'Confidence' },
  'assess.correctness': { zh: '正确性', 'zh-TW': '正確性', en: 'Correctness' },
  'assess.efficiency': { zh: '效率', 'zh-TW': '效率', en: 'Efficiency' },
  'assess.codeStyle': { zh: '代码风格', 'zh-TW': '程式碼風格', en: 'Code Style' },
  'assess.grammar': { zh: '语法', 'zh-TW': '語法', en: 'Grammar' },
  'assess.structure': { zh: '结构', 'zh-TW': '結構', en: 'Structure' },
  'assess.creativity': { zh: '创意', 'zh-TW': '創意', en: 'Creativity' },
  'assess.progressCurve': { zh: '进步曲线', 'zh-TW': '進步曲線', en: 'Progress Curve' },
  'assess.needMoreHistory': { zh: '需要至少2次评估记录才能显示进步曲线', 'zh-TW': '需要至少2次評估記錄才能顯示進步曲線', en: 'At least 2 assessment records needed to show progress curve' },
  'assess.communicationAssess': { zh: '沟通能力评估', 'zh-TW': '溝通能力評估', en: 'Communication Assessment' },
  'assess.commIntro': { zh: '系统将给你一个随机话题，你有 30 秒准备时间，然后 60 秒表达时间。最多可以重试 3 次，系统将评估你的一致性表现。', 'zh-TW': '系統將給你一個隨機話題，你有 30 秒準備時間，然後 60 秒表達時間。最多可以重試 3 次，系統將評估你的一致性表現。', en: 'You will get a random topic, 30s to prepare and 60s to speak. Up to 3 retries; we evaluate your consistent performance.' },
  'assess.recording60': { zh: '60秒录制', 'zh-TW': '60秒錄製', en: '60s recording' },
  'assess.retry3': { zh: '3次重试', 'zh-TW': '3次重試', en: '3 retries' },
  'assess.aiScore': { zh: 'AI评分', 'zh-TW': 'AI評分', en: 'AI scoring' },
  'privacy.pageSubtitle': { zh: '管理你的数据和授权偏好', 'zh-TW': '管理你的資料與授權偏好', en: 'Manage your data and consent preferences' },
  'privacy.rightsTitle': { zh: '你的隐私权利', 'zh-TW': '你的隱私權利', en: 'Your Privacy Rights' },
  'privacy.dataCollectionTitle': { zh: '数据收集', 'zh-TW': '資料收集', en: 'Data Collection' },
  'privacy.dataCollectionDesc': { zh: '我们仅处理你明确上传并授权的文档，数据仅用于技能评估。', 'zh-TW': '我們僅處理你明確上傳並授權的文件，資料僅用於技能評估。', en: 'We only process documents you explicitly upload and consent to. Your data is used solely for skill assessment.' },
  'privacy.securityTitle': { zh: '数据安全', 'zh-TW': '資料安全', en: 'Data Security' },
  'privacy.securityDesc': { zh: '数据在传输和存储时加密，访问受严格控制并审计。', 'zh-TW': '資料在傳輸和儲存時加密，存取受嚴格控制並審計。', en: 'All data is encrypted in transit and at rest. Access is strictly controlled and audited.' },
  'privacy.deletionTitle': { zh: '删除权', 'zh-TW': '刪除權', en: 'Right to Deletion' },
  'privacy.deletionDesc': { zh: '你可随时撤回授权并删除数据，删除为永久且立即生效。', 'zh-TW': '你可隨時撤回授權並刪除資料，刪除為永久且立即生效。', en: 'You can revoke consent and delete your data at any time. Deletion is permanent and immediate.' },
  'privacy.aboutDeletionTitle': { zh: '关于数据删除', 'zh-TW': '關於資料刪除', en: 'About Data Deletion' },
  'privacy.aboutDeletionIntro': { zh: '当你撤回授权时，我们将永久删除：', 'zh-TW': '當你撤回授權時，我們將永久刪除：', en: 'When you revoke consent, we permanently delete:' },
  'privacy.aboutDeletionItem1': { zh: '原始上传文件', 'zh-TW': '原始上傳文件', en: 'The original uploaded file' },
  'privacy.aboutDeletionItem2': { zh: '所有提取的文本与证据片段', 'zh-TW': '所有提取的文本與證據片段', en: 'All extracted text and evidence chunks' },
  'privacy.aboutDeletionItem3': { zh: '基于该文档的所有技能评估', 'zh-TW': '基於該文件的所有技能評估', en: 'All skill assessments based on this document' },
  'privacy.aboutDeletionItem4': { zh: '所有向量与检索索引', 'zh-TW': '所有向量與檢索索引', en: 'All embeddings and search indexes' },
  'privacy.aboutDeletionEnd': { zh: '此操作不可撤销。', 'zh-TW': '此操作不可撤銷。', en: 'This action cannot be undone.' },
  'dashboard.subtitle': { zh: '追踪技能，发现职业路径', 'zh-TW': '追蹤技能，發現職業路徑', en: 'Track your skills and find your career path' },
  'dashboard.visionPitch': { zh: '基于真实证据、面向港大学生、连接学习与就业的智能职业发展系统。', 'zh-TW': '基於真實證據、面向港大學生、連接學習與就業的智能職業發展系統。', en: 'A verified, evidence-based, HKU-specific career intelligence and skills development system.' },
  'dashboard.leaderboardTitle': { zh: '进度排行', 'zh-TW': '進度排行', en: 'Progress Leaderboard' },
  'dashboard.leaderboardDesc': { zh: '与同项目同学对比技能验证进度（匿名）', 'zh-TW': '與同項目同學對比技能驗證進度（匿名）', en: 'Compare skill verification progress with peers (anonymous)' },
  'dashboard.yourRank': { zh: '你的排名', 'zh-TW': '你的排名', en: 'Your rank' },
  'dashboard.topContributors': { zh: '本月领先', 'zh-TW': '本月領先', en: 'Top this month' },
  'dashboard.careerSupport': { zh: '职业支持', 'zh-TW': '職業支援', en: 'Career Support' },
  'dashboard.careerCentreCta': { zh: '预约 HKU 就业中心顾问', 'zh-TW': '預約 HKU 就業中心顧問', en: 'Book HKU Career Centre advisor' },
  'dashboard.prepareSummary': { zh: '准备顾问摘要', 'zh-TW': '準備顧問摘要', en: 'Prepare summary for advisor' },
  'dashboard.summaryForAdvisor': { zh: '顾问摘要', 'zh-TW': '顧問摘要', en: 'Summary for advisor' },
  'dashboard.copyAndClose': { zh: '复制并关闭', 'zh-TW': '複製並關閉', en: 'Copy and close' },
  'dashboard.summaryCopied': { zh: '已复制到剪贴板，可粘贴给顾问。', 'zh-TW': '已複製到剪貼簿，可貼上給顧問。', en: 'Copied to clipboard. You can paste it for your advisor.' },
  'dashboard.downloadTxt': { zh: '下载 .txt', 'zh-TW': '下載 .txt', en: 'Download .txt' },
  'dashboard.careerCentreDesc': { zh: '一对一咨询、简历与面试指导、行业资源', 'zh-TW': '一對一諮詢、履歷與面試指導、行業資源', en: '1-on-1 advising, resume & interview support, industry resources' },
  'dashboard.leaderboardDemoNote': { zh: '（Demo：排行数据接入后显示）', 'zh-TW': '（Demo：排行資料接入後顯示）', en: '(Demo: rank shown when data is connected)' },
  'dashboard.leaderboardPlaceholder': { zh: '（Demo：排行数据接入后显示）', 'zh-TW': '（Demo：排行資料接入後顯示）', en: '(Demo: ranking shown when data is connected)' },
  'dashboard.leaderboardCta': { zh: '完成评估、上传证据可解锁成就并提升排名。', 'zh-TW': '完成評估、上傳證據可解鎖成就並提升排名。', en: 'Complete assessments and upload evidence to unlock achievements and climb the rank.' },
  'dashboard.needEvidence': { zh: '需证据', 'zh-TW': '需證據', en: 'Need Evidence' },
  'dashboard.verifiedBadge': { zh: '已验证', 'zh-TW': '已驗證', en: 'Verified' },
  'dashboard.inProgressBadge': { zh: '进行中', 'zh-TW': '進行中', en: 'In Progress' },
  'dashboard.quickActions': { zh: '快捷操作', 'zh-TW': '快捷操作', en: 'Quick Actions' },
  'dashboard.agentGreeting': { zh: '你好，我是 SkillSight！和我一起做评估，或让我帮你改简历。', 'zh-TW': '你好，我是 SkillSight！和我一起做評估，或讓我幫你改履歷。', en: "Hi, I'm SkillSight! Take an assessment with me, or let me review your resume." },
  'dashboard.startAssessment': { zh: '开始评估', 'zh-TW': '開始評估', en: 'Start Assessment' },
  'dashboard.reviewResume': { zh: '点评简历', 'zh-TW': '點評履歷', en: 'Review My Resume' },
  'dashboard.addDocumentsCode': { zh: '添加文档、项目或代码', 'zh-TW': '添加文件、專案或程式碼', en: 'Add documents, projects, or code' },
  'dashboard.seeReadiness': { zh: '查看你的职位就绪度', 'zh-TW': '查看你的職位就緒度', en: 'See your readiness for roles' },
  'dashboard.assessDesc': { zh: '沟通、编程、写作', 'zh-TW': '溝通、程式設計、寫作', en: 'Communication, Coding, Writing' },
  'dashboard.noDocumentsYet': { zh: '暂无文档', 'zh-TW': '暫無文件', en: 'No documents yet' },
  'dashboard.uploadFirstDocument': { zh: '上传第一份文档即可开始', 'zh-TW': '上傳第一份文件即可開始', en: 'Upload your first document to get started' },
  'dashboard.uploadNow': { zh: '立即上传', 'zh-TW': '立即上傳', en: 'Upload Now' },
  'dashboard.noSkillsYet': { zh: '暂无技能记录', 'zh-TW': '暫無技能記錄', en: 'No skills tracked yet' },
  'dashboard.uploadEvidenceToStart': { zh: '上传证据以开始建立技能档案', 'zh-TW': '上傳證據以開始建立技能檔案', en: 'Upload evidence to start building your skill profile' },
  'dashboard.processed': { zh: '已处理', 'zh-TW': '已處理', en: 'Processed' },
  'dashboard.level': { zh: '等级', 'zh-TW': '等級', en: 'Level' },
  'dashboard.evidenceItems': { zh: '条证据', 'zh-TW': '條證據', en: 'evidence items' },
  'dashboard.itemsUnderReview': { zh: '项审核中', 'zh-TW': '項審核中', en: 'items under review' },
  'dashboard.noEvidence': { zh: '无证据', 'zh-TW': '無證據', en: 'No evidence' },
  'dashboard.viewEvidence': { zh: '查看证据', 'zh-TW': '查看證據', en: 'View evidence' },
  'dashboard.personalizedLearningPath': { zh: '个性化学习路径', 'zh-TW': '個性化學習路徑', en: 'Personalized Learning Path' },
  'dashboard.timeJustNow': { zh: '刚刚', 'zh-TW': '剛剛', en: 'Just now' },
  'dashboard.hoursAgo': { zh: '小时前', 'zh-TW': '小時前', en: 'h ago' },
  'dashboard.daysAgo': { zh: '天前', 'zh-TW': '天前', en: 'd ago' },
  'dashboard.learnMore': { zh: '了解更多', 'zh-TW': '了解更多', en: 'Learn More' },
  'dashboard.startNow': { zh: '立即开始', 'zh-TW': '立即開始', en: 'Start Now' },
  'dashboard.takePythonCourse': { zh: '修读 Python 课程', 'zh-TW': '修讀 Python 課程', en: 'Take Python Course' },
  'dashboard.completeCOMP7404': { zh: '完成 COMP7404 以加强编程能力', 'zh-TW': '完成 COMP7404 以加強程式設計能力', en: 'Complete COMP7404 to strengthen your programming skills' },
  'dashboard.communicationAssessment': { zh: '沟通能力评估', 'zh-TW': '溝通能力評估', en: 'Communication Assessment' },
  'dashboard.completeVideoAssessment': { zh: '完成视频评估以验证沟通能力', 'zh-TW': '完成影片評估以驗證溝通能力', en: 'Complete the video assessment to verify communication skills' },
  'dashboard.addDataProject': { zh: '添加数据项目', 'zh-TW': '添加資料專案', en: 'Add Data Project' },
  'dashboard.uploadDataProjectDesc': { zh: '上传数据分析项目作为分析技能的证据', 'zh-TW': '上傳資料分析專案作為分析技能的證據', en: 'Upload a data analysis project as evidence for analytics skills' },
  'dashboard.upload': { zh: '上传', 'zh-TW': '上傳', en: 'Upload' },
  'changelog.pageTitle': { zh: '变更日志', 'zh-TW': '變更日誌', en: 'Change Log' },
  'changelog.loginToView': { zh: '请登录后查看变更日志。', 'zh-TW': '請登入後查看變更日誌。', en: 'Please log in to view the change log.' },
  'changelog.loadFailedGeneric': { zh: '加载变更日志失败', 'zh-TW': '載入變更日誌失敗', en: 'Failed to load change log' },

  // 技能雷达图
  'skills.radar': { zh: '技能雷达图', 'zh-TW': '技能雷達圖', en: 'Skills Radar' },
  'skills.compare': { zh: '技能对比', 'zh-TW': '技能對比', en: 'Skills Comparison' },
  'skills.withPeers': { zh: '与同行对比', 'zh-TW': '與同行對比', en: 'Compare with Peers' },
  'skills.withRole': { zh: '与目标岗位对比', 'zh-TW': '與目標職位對比', en: 'Compare with Target Role' },
  'skills.yourLevel': { zh: '你的水平', 'zh-TW': '你的水準', en: 'Your Level' },
  'skills.targetLevel': { zh: '目标水平', 'zh-TW': '目標水準', en: 'Target Level' },
  'skills.peerAvg': { zh: '同行平均', 'zh-TW': '同行平均', en: 'Peer Average' },
  'skills.minRequired': { zh: '至少需要3项技能', 'zh-TW': '至少需要3項技能', en: 'At least 3 skills required' },
  'skills.verified': { zh: '已验证', 'zh-TW': '已驗證', en: 'Verified' },
  'skills.mentioned': { zh: '已提及', 'zh-TW': '已提及', en: 'Mentioned' },
  'skills.insufficient': { zh: '证据不足', 'zh-TW': '證據不足', en: 'Insufficient Evidence' },
  'skills.tutorChat': { zh: '与 AI Tutor 对话', 'zh-TW': '與 AI Tutor 對話', en: 'Chat with AI Tutor' },
  'skills.tutorTitle': { zh: 'AI Tutor 补证对话', 'zh-TW': 'AI Tutor 補證對話', en: 'AI Tutor Evidence Chat' },
  'skills.tutorPlaceholder': { zh: '输入你的经历或说明…', 'zh-TW': '輸入你的經歷或說明…', en: 'Describe your experience…' },
  'skills.tutorPlaceholderAssessment': { zh: '简要回复与评估相关的内容…', 'zh-TW': '簡要回覆與評估相關的內容…', en: 'Reply about the assessment (brief)…' },
  'skills.tutorTurnLimit': { zh: '已达对话轮数上限，等待评估结果。', 'zh-TW': '已達對話輪數上限，等待評估結果。', en: 'Turn limit reached. Waiting for assessment.' },
  'skills.tutorSend': { zh: '发送', 'zh-TW': '傳送', en: 'Send' },
  'skills.tutorClose': { zh: '关闭', 'zh-TW': '關閉', en: 'Close' },
  'skills.tutorConcluded': { zh: '已根据对话更新技能评估', 'zh-TW': '已根據對話更新技能評估', en: 'Assessment updated from this chat' },
  'skills.tutorError': { zh: '发送失败，请重试。', 'zh-TW': '傳送失敗，請重試。', en: 'Something went wrong. Please try again.' },
  'skills.unassessed': { zh: '未评估', 'zh-TW': '未評估', en: 'Unassessed' },
  'skills.exportStatement': { zh: '导出声明', 'zh-TW': '匯出聲明', en: 'Export Statement' },
  'skills.refresh': { zh: '刷新', 'zh-TW': '重新整理', en: 'Refresh' },
  'skills.authorizedDocs': { zh: '份已授权文档', 'zh-TW': '份已授權文件', en: 'authorized documents' },
  'skills.generatedAt': { zh: '生成于', 'zh-TW': '生成於', en: 'Generated at' },
  'skills.all': { zh: '全部', 'zh-TW': '全部', en: 'All' },
  'skills.searchPlaceholder': { zh: '搜索技能...', 'zh-TW': '搜尋技能...', en: 'Search skills...' },
  'skills.loading': { zh: '加载中...', 'zh-TW': '載入中...', en: 'Loading...' },
  'skills.loadingSlowHint': { zh: '正在连接服务器，首次加载可能需要 10–20 秒，请稍候。', 'zh-TW': '正在連接伺服器，首次載入可能需要 10–20 秒，請稍候。', en: 'Connecting to server; first load may take 10–20 seconds.' },
  'skills.loadFailed': { zh: '加载失败', 'zh-TW': '載入失敗', en: 'Load Failed' },
  'skills.loginRequired': { zh: '请先登录以查看技能档案。', 'zh-TW': '請先登入以查看技能檔案。', en: 'Please log in to view your skill profile.' },
  'skills.loadFailedMsg': { zh: '请确认已上传文档并登录，然后重试。', 'zh-TW': '請確認已上傳文件並登入，然後重試。', en: 'Please confirm you have uploaded documents and are logged in, then try again.' },
  'skills.networkErrorHint': { zh: '无法连接服务器，请稍后重试或联系支持。', 'zh-TW': '無法連接伺服器，請稍後重試或聯絡支援。', en: 'Cannot reach the server. Please try again later or contact support.' },
  'skills.retry': { zh: '重试', 'zh-TW': '重試', en: 'Retry' },
  'skills.noMatch': { zh: '暂无匹配技能', 'zh-TW': '暫無匹配技能', en: 'No matching skills' },
  'skills.uploadFirst': { zh: '请先', 'zh-TW': '請先', en: 'Please' },
  'skills.uploadDoc': { zh: '上传文档', 'zh-TW': '上傳文件', en: 'upload a document' },
  'skills.andRunAssess': { zh: '并运行 AI 评估。', 'zh-TW': '並執行 AI 評估。', en: 'and run an AI assessment.' },
  'skills.evidence': { zh: '条证据', 'zh-TW': '條證據', en: 'evidence' },
  'skills.noEvidence': { zh: '无证据', 'zh-TW': '無證據', en: 'No evidence' },
  'skills.whyReason': { zh: 'WHY（评估理由）', 'zh-TW': 'WHY（評估理由）', en: 'WHY (Assessment Reason)' },
  'skills.evidenceSnippet': { zh: 'EVIDENCE（证据片段）', 'zh-TW': 'EVIDENCE（證據片段）', en: 'EVIDENCE (Snippet)' },
  'skills.viewSource': { zh: '查看原文位置 →', 'zh-TW': '查看原文位置 →', en: 'View Source Location →' },
  'skills.needMoreInfo': { zh: '需要更多信息', 'zh-TW': '需要更多資訊', en: 'More information needed' },
  'agent.resumeReview': { zh: '简历点评', 'zh-TW': '履歷點評', en: 'Review My Resume' },
  'agent.greeting': { zh: '你好！我是 SkillSight，你的个人评估助手。\n\n你可以：\na) 通过对话进行技能评估\nb) 让我帮你点评和改进简历\nc) 了解你的技能差距与提升方向\n\n如需真人支持：\n预约 HKU 就业中心顾问\n\n你想先做哪一项？', 'zh-TW': '你好！我是 SkillSight，你的個人評估助手。\n\n你可以：\na) 透過對話進行技能評估\nb) 讓我幫你點評與改進履歷\nc) 了解你的技能差距與提升方向\n\n如需真人支援：\n預約 HKU 就業中心顧問\n\n你想先做哪一項？', en: 'Hi! I\'m SkillSight, your personal assessment agent.\n\nHere\'s how I can help:\na) Assess your skills through a guided conversation\nb) Review and improve your resume\nc) Help you understand your skill gaps\n\nOr, if you\'d like human support:\nConnect with HKU Career Centre staff\n\nWhat would you like to start with?' },
  'agent.careerBar': { zh: '需要真人帮助？ 预约 HKU 就业中心顾问', 'zh-TW': '需要真人協助？ 預約 HKU 就業中心顧問', en: 'Need human support? Book HKU Career Centre advisor' },
  'agent.justNow': { zh: '刚刚', 'zh-TW': '剛剛', en: 'Just now' },
  'agent.minAgo': { zh: '1 分钟前', 'zh-TW': '1 分鐘前', en: '1 min ago' },
  'agent.minsAgo': { zh: '分钟前', 'zh-TW': '分鐘前', en: 'mins ago' },
  'agent.retry': { zh: '重试', 'zh-TW': '重試', en: 'Retry' },
  'agent.sessionStartFailed': { zh: '无法连接评估服务，请检查网络后重试。', 'zh-TW': '無法連接評估服務，請檢查網路後重試。', en: 'Could not connect to the assessment service. Please check your network and try again.' },
  'agent.noContextHint': { zh: '在「评估」页选择具体类型后，可获得更针对性的评估。', 'zh-TW': '在「評估」頁選擇具體類型後，可獲得更具針對性的評估。', en: 'Choose a specific type on the Assessments page for a more targeted assessment.' },
  'agent.noContextLink': { zh: '去选择', 'zh-TW': '去選擇', en: 'Choose type' },
  'agent.turnLimitGreeting': { zh: '本轮评估约 10 轮对话内完成。', 'zh-TW': '本輪評估約 10 輪對話內完成。', en: 'This assessment usually completes within about 10 exchanges.' },
  'skills.nextStep': { zh: '下一步：', 'zh-TW': '下一步：', en: 'Next step:' },
  'skills.uploadEvidence': { zh: '上传证据', 'zh-TW': '上傳證據', en: 'Upload Evidence' },
  'skills.claimHint': { zh: '每个技能 claim 都附有 Why / Evidence —— 展开查看来源片段与定位信息', 'zh-TW': '每個技能 claim 都附有 Why / Evidence —— 展開查看來源片段與定位資訊', en: 'Each skill claim includes Why / Evidence — expand to view source snippets and location info' },
  'skills.profileTitle': { zh: '技能档案', 'zh-TW': '技能檔案', en: 'Skills Profile' },

  // 学习路径
  'learning.path': { zh: '学习路径', 'zh-TW': '學習路徑', en: 'Learning Path' },
  'learning.recommended': { zh: '推荐学习', 'zh-TW': '推薦學習', en: 'Recommended Learning' },
  'learning.priority': { zh: '优先级', 'zh-TW': '優先級', en: 'Priority' },
  'learning.high': { zh: '高', 'zh-TW': '高', en: 'High' },
  'learning.medium': { zh: '中', 'zh-TW': '中', en: 'Medium' },
  'learning.low': { zh: '低', 'zh-TW': '低', en: 'Low' },
  'learning.duration': { zh: '预计时长', 'zh-TW': '預計時長', en: 'Est. Duration' },
  'learning.startLearning': { zh: '开始学习', 'zh-TW': '開始學習', en: 'Start Learning' },
  'learning.typeCourse': { zh: '课程', 'zh-TW': '課程', en: 'Course' },
  'learning.typeProject': { zh: '项目', 'zh-TW': '專案', en: 'Project' },
  'learning.typeAssessment': { zh: '评估', 'zh-TW': '評估', en: 'Assessment' },
  'learning.typeResource': { zh: '资源', 'zh-TW': '資源', en: 'Resource' },
  'learning.priorityHigh': { zh: '高优先', 'zh-TW': '高優先', en: 'High Priority' },
  'learning.priorityMedium': { zh: '中等', 'zh-TW': '中等', en: 'Medium' },
  'learning.priorityLow': { zh: '推荐', 'zh-TW': '推薦', en: 'Recommended' },
  'learning.generating': { zh: '正在生成个性化学习路径...', 'zh-TW': '正在生成個性化學習路徑...', en: 'Generating personalized learning path...' },
  'learning.noSuggestions': { zh: '暂无学习建议', 'zh-TW': '暫無學習建議', en: 'No learning recommendations' },
  'learning.uploadMore': { zh: '上传更多证据文档来获取个性化推荐', 'zh-TW': '上傳更多證據文件來獲取個性化推薦', en: 'Upload more evidence documents for personalized recommendations' },
  'learning.viewAll': { zh: '查看全部', 'zh-TW': '查看全部', en: 'View all' },
  'learning.suggestions': { zh: '个建议', 'zh-TW': '個建議', en: 'suggestions' },
  'learning.analyzing': { zh: '正在分析技能差距并生成学习路径...', 'zh-TW': '正在分析技能差距並生成學習路徑...', en: 'Analyzing skill gaps and generating learning path...' },
  'learning.skillGapTitle': { zh: '技能差距分析', 'zh-TW': '技能差距分析', en: 'Skill Gap Analysis' },
  'learning.excellent': { zh: '🎉 恭喜！你的技能水平已经很高了', 'zh-TW': '🎉 恭喜！你的技能水準已經很高了', en: '🎉 Congratulations! Your skill level is already excellent' },
  'learning.current': { zh: '当前 Lv.', 'zh-TW': '當前 Lv.', en: 'Current Lv.' },
  'learning.target': { zh: '目标 Lv.', 'zh-TW': '目標 Lv.', en: 'Target Lv.' },
  'learning.pathTitle': { zh: '推荐学习路径', 'zh-TW': '推薦學習路徑', en: 'Recommended Learning Path' },
  'learning.count': { zh: '个建议', 'zh-TW': '個建議', en: 'recommendations' },

  // 成就系统
  'achievements.title': { zh: '成就', 'zh-TW': '成就', en: 'Achievements' },
  'achievements.badges': { zh: '徽章', 'zh-TW': '徽章', en: 'Badges' },
  'achievements.milestones': { zh: '里程碑', 'zh-TW': '里程碑', en: 'Milestones' },
  'achievements.unlocked': { zh: '已解锁', 'zh-TW': '已解鎖', en: 'Unlocked' },
  'achievements.locked': { zh: '未解锁', 'zh-TW': '未解鎖', en: 'Locked' },
  'achievements.progress': { zh: '进度', 'zh-TW': '進度', en: 'Progress' },
  'achievements.points': { zh: '积分', 'zh-TW': '積分', en: 'Points' },
  'achievements.system': { zh: '成就系统', 'zh-TW': '成就系統', en: 'Achievement System' },
  'achievements.common': { zh: '普通', 'zh-TW': '普通', en: 'Common' },
  'achievements.rare': { zh: '稀有', 'zh-TW': '稀有', en: 'Rare' },
  'achievements.epic': { zh: '史诗', 'zh-TW': '史詩', en: 'Epic' },
  'achievements.legendary': { zh: '传说', 'zh-TW': '傳說', en: 'Legendary' },
  'achievements.unlockedAt': { zh: '✓ 解锁于', 'zh-TW': '✓ 解鎖於', en: '✓ Unlocked on' },
  'achievements.assessmentTab': { zh: '评估成就', 'zh-TW': '評估成就', en: 'Assessment' },
  'achievements.learningTab': { zh: '学习成就', 'zh-TW': '學習成就', en: 'Learning' },
  'achievements.milestonesTab': { zh: '里程碑', 'zh-TW': '里程碑', en: 'Milestones' },
  'achievements.specialTab': { zh: '特殊成就', 'zh-TW': '特殊成就', en: 'Special' },
  'achievements.notification': { zh: '🎉 成就解锁！', 'zh-TW': '🎉 成就解鎖！', en: '🎉 Achievement Unlocked!' },

  // 分享
  'share.title': { zh: '分享技能证书', 'zh-TW': '分享技能證書', en: 'Share Skills Certificate' },
  'share.download': { zh: '下载图片', 'zh-TW': '下載圖片', en: 'Download Image' },
  'share.copyLink': { zh: '复制链接', 'zh-TW': '複製連結', en: 'Copy Link' },
  'share.certificate': { zh: '技能证书', 'zh-TW': '技能證書', en: 'Skills Certificate' },
  'share.button': { zh: '分享', 'zh-TW': '分享', en: 'Share' },
  'share.shareProfile': { zh: '分享技能档案', 'zh-TW': '分享技能檔案', en: 'Share Skills Profile' },
  'share.skillProfile': { zh: '技能评估档案', 'zh-TW': '技能評估檔案', en: 'Skills Assessment Profile' },
  'share.overallScore': { zh: '综合技能得分', 'zh-TW': '綜合技能得分', en: 'Overall Skills Score' },
  'share.profileOf': { zh: '的技能档案 - SkillSight', 'zh-TW': '的技能檔案 - SkillSight', en: '\'s Skills Profile - SkillSight' },
  'share.nativeShareText': { zh: '查看 {{name}} 的技能评估结果，综合得分 {{score}}%', 'zh-TW': '查看 {{name}} 的技能評估結果，綜合得分 {{score}}%', en: 'View {{name}}\'s skills assessment result, overall score {{score}}%' },
  'share.noHtml2canvas': { zh: '图片生成功能需要安装 html2canvas 库', 'zh-TW': '圖片生成功能需要安裝 html2canvas 庫', en: 'Image generation requires the html2canvas library' },

  // 引导教程
  'tutorial.welcome': { zh: '欢迎使用 SkillSight！', 'zh-TW': '歡迎使用 SkillSight！', en: 'Welcome to SkillSight!' },
  'tutorial.step1': { zh: '上传你的作品、项目或文档作为技能证据', 'zh-TW': '上傳你的作品、專案或文件作為技能證據', en: 'Upload your work, projects, or documents as skill evidence' },
  'tutorial.step2': { zh: '完成交互式评估来验证你的能力', 'zh-TW': '完成互動式評估來驗證你的能力', en: 'Complete interactive assessments to verify your abilities' },
  'tutorial.step3': { zh: '查看你的技能档案和职位匹配', 'zh-TW': '查看你的技能檔案和職位匹配', en: 'View your skill profile and job matches' },
  'tutorial.step4': { zh: '获取个性化的学习建议', 'zh-TW': '獲取個性化的學習建議', en: 'Get personalized learning recommendations' },
  'tutorial.helloTitle': { zh: 'Hi，我是 SkillSight！', 'zh-TW': 'Hi，我是 SkillSight！', en: 'Hi, I am SkillSight!' },
  'tutorial.helloDesc': { zh: '我会帮你把作品和经历转成可验证的技能档案。先设置你的名字和语言，马上开始。', 'zh-TW': '我會幫你把作品和經歷轉成可驗證的技能檔案。先設定你的名字和語言，馬上開始。', en: 'I help convert your work into verifiable skill evidence. Set your name and language to get started.' },
  'tutorial.uploadTitle': { zh: '先上传技能证据', 'zh-TW': '先上傳技能證據', en: 'Start by Uploading Evidence' },
  'tutorial.uploadDesc': { zh: '支持文档、代码、图片、音视频、表格和 Notebook。上传后系统会自动解析与分段。', 'zh-TW': '支援文件、程式碼、圖片、音影片、表格與 Notebook。上傳後系統會自動解析與分段。', en: 'Upload docs, code, images, media, spreadsheets, and notebooks. We parse and chunk them automatically.' },
  'tutorial.assessTitle': { zh: '再做互动评估', 'zh-TW': '再做互動評估', en: 'Then Complete Assessments' },
  'tutorial.assessDesc': { zh: '通过沟通、编程、写作评估补充证据，让技能结论更稳定。', 'zh-TW': '透過溝通、程式設計、寫作評估補充證據，讓技能結論更穩定。', en: 'Add stronger proof through communication, coding, and writing assessments.' },
  'tutorial.profileTitle': { zh: '查看技能档案与匹配', 'zh-TW': '查看技能檔案與匹配', en: 'Review Profile and Matches' },
  'tutorial.profileDesc': { zh: '在技能档案页看每项技能证据，在职位匹配页看就绪度和差距。', 'zh-TW': '在技能檔案頁看每項技能證據，在職位匹配頁看就緒度和差距。', en: 'Inspect skill evidence in profile view and readiness gaps in job matching.' },
  'tutorial.routeTitle': { zh: '推荐操作路线', 'zh-TW': '推薦操作路線', en: 'Suggested First Route' },
  'tutorial.routeDesc': { zh: '按这条路线走一遍，你就能快速上手 SkillSight。', 'zh-TW': '按這條路線走一遍，你就能快速上手 SkillSight。', en: 'Follow this short route once and you will get comfortable quickly.' },
  'tutorial.routeFlow': { zh: '上传证据 -> 参加评估 -> 查看技能档案 -> 查看职位匹配 -> 学习建议', 'zh-TW': '上傳證據 -> 參加評估 -> 查看技能檔案 -> 查看職位匹配 -> 學習建議', en: 'Upload evidence -> Assessments -> Skills profile -> Job matching -> Learning path' },
  'tutorial.nameLabel': { zh: '你的昵称', 'zh-TW': '你的暱稱', en: 'Your display name' },
  'tutorial.namePlaceholder': { zh: '例如：Alex / 小明', 'zh-TW': '例如：Alex / 小明', en: 'Example: Alex' },
  'tutorial.languageLabel': { zh: '选择语言', 'zh-TW': '選擇語言', en: 'Choose language' },
  'tutorial.next': { zh: '下一步', 'zh-TW': '下一步', en: 'Next' },
  'tutorial.prev': { zh: '上一步', 'zh-TW': '上一步', en: 'Previous' },
  'tutorial.skip': { zh: '跳过教程', 'zh-TW': '略過教學', en: 'Skip Tutorial' },
  'tutorial.finish': { zh: '开始使用', 'zh-TW': '開始使用', en: 'Get Started' },

  // 设置
  'settings.theme': { zh: '主题', 'zh-TW': '主題', en: 'Theme' },
  'settings.light': { zh: '浅色', 'zh-TW': '淺色', en: 'Light' },
  'settings.dark': { zh: '深色', 'zh-TW': '深色', en: 'Dark' },
  'settings.language': { zh: '语言', 'zh-TW': '語言', en: 'Language' },
  'settings.chinese': { zh: '简体中文', 'zh-TW': '簡體中文', en: 'Simplified Chinese' },
  'settings.chineseTW': { zh: '繁体中文', 'zh-TW': '繁體中文', en: 'Traditional Chinese' },
  'settings.english': { zh: '英文', 'zh-TW': '英文', en: 'English' },
  'settings.pageTitle': { zh: '设置', 'zh-TW': '設定', en: 'Settings' },
  'settings.pageSubtitle': { zh: '管理你的账户与偏好', 'zh-TW': '管理你的帳戶與偏好', en: 'Manage your account and preferences' },
  'settings.profile': { zh: '👤 个人资料', 'zh-TW': '👤 個人資料', en: '👤 Profile' },
  'settings.displayName': { zh: '显示名称', 'zh-TW': '顯示名稱', en: 'Display Name' },
  'settings.email': { zh: '邮箱', 'zh-TW': '電郵', en: 'Email' },
  'settings.saveChanges': { zh: '保存更改', 'zh-TW': '儲存變更', en: 'Save Changes' },
  'settings.notifications': { zh: '🔔 通知', 'zh-TW': '🔔 通知', en: '🔔 Notifications' },
  'settings.emailNotif': { zh: '邮件通知', 'zh-TW': '郵件通知', en: 'Email Notifications' },
  'settings.emailNotifDesc': { zh: '通过邮件接收更新', 'zh-TW': '透過郵件接收更新', en: 'Receive updates via email' },
  'settings.skillUpdates': { zh: '技能更新', 'zh-TW': '技能更新', en: 'Skill Updates' },
  'settings.skillUpdatesDesc': { zh: '当技能评估完成时', 'zh-TW': '當技能評估完成時', en: 'When a skill assessment is completed' },
  'settings.reviewComplete': { zh: '审核完成', 'zh-TW': '審核完成', en: 'Review Complete' },
  'settings.reviewCompleteDesc': { zh: '当工作人员完成对你的提交审核时', 'zh-TW': '當工作人員完成對你的提交審核時', en: 'When a staff member reviews your submission' },
  'settings.weeklyDigest': { zh: '每周摘要', 'zh-TW': '每週摘要', en: 'Weekly Digest' },
  'settings.weeklyDigestDesc': { zh: '你的进度每周摘要', 'zh-TW': '你的進度每週摘要', en: 'Weekly summary of your progress' },
  'settings.quickLinks': { zh: '⚡ 快捷链接', 'zh-TW': '⚡ 快捷連結', en: '⚡ Quick Links' },
  'settings.privacyData': { zh: '隐私与数据', 'zh-TW': '隱私與資料', en: 'Privacy & Data' },
  'settings.privacyDataDesc': { zh: '管理你的数据与授权', 'zh-TW': '管理你的資料與授權', en: 'Manage your data and consent' },
  'settings.viewSkillProfile': { zh: '查看你的技能档案', 'zh-TW': '查看你的技能檔案', en: 'View your skill profile' },
  'settings.signOut': { zh: '🚪 退出登录', 'zh-TW': '🚪 登出', en: '🚪 Sign Out' },
  'settings.administrator': { zh: '管理员', 'zh-TW': '管理員', en: 'Administrator' },

  // 登录页
  'login.subtitle': { zh: 'HKU 技能与职业透明系统', 'zh-TW': 'HKU 技能與職業透明系統', en: 'HKU Skills-to-Jobs Transparency System' },
  'login.student': { zh: '👨‍🎓 学生', 'zh-TW': '👨‍🎓 學生', en: '👨‍🎓 Student' },
  'login.adminStaff': { zh: '👩‍💼 管理员/教职工', 'zh-TW': '👩‍💼 管理員/教職工', en: '👩‍💼 Admin/Staff' },
  'login.connecting': { zh: '连接中...', 'zh-TW': '連線中...', en: 'Connecting...' },
  'login.signInHKU': { zh: '🔐 使用 HKU 门户登录', 'zh-TW': '🔐 使用 HKU 門戶登入', en: '🔐 Sign in with HKU Portal' },
  'login.or': { zh: '或', 'zh-TW': '或', en: 'or' },
  'login.emailPlaceholder': { zh: '邮箱地址', 'zh-TW': '電郵地址', en: 'Email address' },
  'login.continueEmail': { zh: '使用邮箱继续', 'zh-TW': '使用電郵繼續', en: 'Continue with Email' },
  'login.needHelp': { zh: '需要帮助？', 'zh-TW': '需要幫助？', en: 'Need help?' },
  'login.contactUs': { zh: '联系我们', 'zh-TW': '聯絡我們', en: 'Contact us' },
  'login.failedNetwork': { zh: '无法连接服务器，请检查网络后重试或联系支持。', 'zh-TW': '無法連接伺服器，請檢查網路後重試或聯絡支援。', en: 'Cannot connect. Please check your network and try again, or contact support.' },
  'assistant.loginRequired': { zh: '请先登录以使用评估助手', 'zh-TW': '請先登入以使用評估助手', en: 'Please log in to use the assessment assistant' },
  'assistant.goLogin': { zh: '去登录', 'zh-TW': '前往登入', en: 'Go to Login' },

  // 评估列表页
  'assessmentsList.pageTitle': { zh: '技能评估', 'zh-TW': '技能評估', en: 'Skill Assessments' },
  'assessmentsList.pageSubtitle': { zh: '通过互动测试展示你的能力', 'zh-TW': '透過互動測試展示你的能力', en: 'Demonstrate your abilities through interactive tests' },
  'assessmentsList.complete': { zh: '评估完成！', 'zh-TW': '評估完成！', en: 'Assessment Complete!' },
  'assessmentsList.assessmentUpdated': { zh: '评估已更新', 'zh-TW': '評估已更新', en: 'Assessment updated.' },
  'assessmentsList.viewSkillProfile': { zh: '查看技能档案', 'zh-TW': '查看技能檔案', en: 'View skills profile' },
  'assessmentsList.tryAnother': { zh: '再测一次', 'zh-TW': '再測一次', en: 'Try Another Assessment' },
  'assessmentsList.chooseType': { zh: '选择评估类型', 'zh-TW': '選擇評估類型', en: 'Choose Assessment Type' },
  'assessmentsList.videoResponse': { zh: '视频作答评估', 'zh-TW': '影片作答評估', en: 'Video response assessment' },
  'assessmentsList.algorithmChallenges': { zh: '算法挑战', 'zh-TW': '演算法挑戰', en: 'Algorithm challenges' },
  'assessmentsList.timedEssay': { zh: '限时写作', 'zh-TW': '限時寫作', en: 'Timed essay writing' },
  'assessmentsList.selected': { zh: '已选', 'zh-TW': '已選', en: 'Selected' },
  'assessmentsList.clickToSelect': { zh: '点击选择', 'zh-TW': '點擊選擇', en: 'Click to select' },
  'assessmentsList.selectDifficulty': { zh: '选择难度：', 'zh-TW': '選擇難度：', en: 'Select Difficulty:' },
  'assessmentsList.startAssessment': { zh: '🚀 开始评估', 'zh-TW': '🚀 開始評估', en: '🚀 Start Assessment' },
  'assessmentsList.starting': { zh: '启动中...', 'zh-TW': '啟動中...', en: 'Starting...' },
  'assessmentsList.cancel': { zh: '✕ 取消', 'zh-TW': '✕ 取消', en: '✕ Cancel' },
  'assessmentsList.yourTopic': { zh: '📌 你的话题', 'zh-TW': '📌 你的話題', en: '📌 Your Topic' },
  'assessmentsList.startRecording': { zh: '▶️ 开始录制', 'zh-TW': '▶️ 開始錄製', en: '▶️ Start Recording' },
  'assessmentsList.stopRecording': { zh: '⏹️ 停止录制', 'zh-TW': '⏹️ 停止錄製', en: '⏹️ Stop Recording' },
  'assessmentsList.submitResponse': { zh: '📤 提交作答', 'zh-TW': '📤 提交作答', en: '📤 Submit Response' },
  'assessmentsList.submitting': { zh: '提交中...', 'zh-TW': '提交中...', en: 'Submitting...' },
  'assessmentsList.transcribing': { zh: '转录中...', 'zh-TW': '轉錄中...', en: 'Transcribing...' },
  'assessmentsList.transcriptReady': { zh: '转录完成，可点击提交。', 'zh-TW': '轉錄完成，可點擊提交。', en: 'Transcript ready. Click submit when ready.' },
  'assessmentsList.yourSolution': { zh: '你的解答 (Python)', 'zh-TW': '你的解答 (Python)', en: 'Your Solution (Python)' },
  'assessmentsList.submitSolution': { zh: '📤 提交解答', 'zh-TW': '📤 提交解答', en: '📤 Submit Solution' },
  'assessmentsList.evaluating': { zh: '评估中...', 'zh-TW': '評估中...', en: 'Evaluating...' },
  'assessmentsList.yourEssay': { zh: '你的文章', 'zh-TW': '你的文章', en: 'Your Essay' },
  'assessmentsList.submitEssay': { zh: '📤 提交文章', 'zh-TW': '📤 提交文章', en: '📤 Submit Essay' },
  'assessmentsList.couldNotStart': { zh: '无法启动评估，请检查后端是否运行。', 'zh-TW': '無法啟動評估，請檢查後端是否運行。', en: 'Could not start assessment. Please check if the backend is running.' },
  'assessmentsList.networkError': { zh: '无法连接评估服务，请检查网络后重试。', 'zh-TW': '無法連接評估服務，請檢查網路後重試。', en: 'Could not connect to the assessment service. Please check your network and try again.' },
  'assessmentsList.submissionFailed': { zh: '提交失败', 'zh-TW': '提交失敗', en: 'Submission failed' },
  'assessmentsList.time1_2': { zh: '1-2 分钟', 'zh-TW': '1-2 分鐘', en: '1-2 minutes' },
  'assessmentsList.time15_30': { zh: '15-30 分钟', 'zh-TW': '15-30 分鐘', en: '15-30 minutes' },
  'assessmentsList.time30': { zh: '30 分钟', 'zh-TW': '30 分鐘', en: '30 minutes' },
  'assessmentsList.randomTopic': { zh: '随机话题', 'zh-TW': '隨機話題', en: 'Random topic' },
  'assessmentsList.speakFreely': { zh: '自由表达', 'zh-TW': '自由表達', en: 'Speak freely' },
  'assessmentsList.upTo3Retries': { zh: '最多 3 次重试', 'zh-TW': '最多 3 次重試', en: 'Up to 3 retries' },
  'assessmentsList.aiEval': { zh: 'AI 评估', 'zh-TW': 'AI 評估', en: 'AI evaluation' },
  'assessmentsList.difficultyLevels': { zh: '3 档难度', 'zh-TW': '3 檔難度', en: '3 difficulty levels' },
  'assessmentsList.realWorldProblems': { zh: '真实问题', 'zh-TW': '真實問題', en: 'Real-world problems' },
  'assessmentsList.codeAnalysis': { zh: '代码分析', 'zh-TW': '程式碼分析', en: 'Code analysis' },
  'assessmentsList.instantFeedback': { zh: '即时反馈', 'zh-TW': '即時回饋', en: 'Instant feedback' },
  'assessmentsList.words300_500': { zh: '300-500 字', 'zh-TW': '300-500 字', en: '300-500 words' },
  'assessmentsList.antiCopy': { zh: '防抄袭', 'zh-TW': '防抄襲', en: 'Anti-copy protection' },
  'assessmentsList.styleFeedback': { zh: '风格反馈', 'zh-TW': '風格回饋', en: 'Style feedback' },
  'assessmentsList.descComm': { zh: '你将收到一个随机话题，有 30 秒准备时间，然后最多 60 秒作答。', 'zh-TW': '你將收到一個隨機話題，有 30 秒準備時間，然後最多 60 秒作答。', en: 'You will receive a random topic. After 30 seconds of preparation, speak for up to 60 seconds.' },
  'assessmentsList.descProg': { zh: '根据所选难度完成一道编程题，时限因难度而异。', 'zh-TW': '根據所選難度完成一道程式設計題，時限因難度而異。', en: 'Solve a coding problem at the selected difficulty. Time limit varies by difficulty.' },
  'assessmentsList.descWriting': { zh: '在 30 分钟内就给定主题写一篇 300-500 字的文章，请直接输入。', 'zh-TW': '在 30 分鐘內就給定主題寫一篇 300-500 字的文章，請直接輸入。', en: 'Write a 300-500 word essay on a given topic within 30 minutes. Type your response directly.' },
  'assessmentsList.challenge': { zh: '挑战', 'zh-TW': '挑戰', en: 'Challenge' },
  'assessmentsList.recentUpdatesTitle': { zh: '最近评估更新', 'zh-TW': '最近評估更新', en: 'Recent Assessment Updates' },
  'assessmentsList.recentUpdatesHint': { zh: '你刚完成的评估会同步更新到技能档案。', 'zh-TW': '你剛完成的評估會同步更新到技能檔案。', en: 'Completed assessments are synced to your skill profile.' },
  'assessmentsList.updatedSkillNow': { zh: '已更新技能', 'zh-TW': '已更新技能', en: 'Skill Updated' },
  'assessmentsList.noRecentUpdates': { zh: '暂无最近更新', 'zh-TW': '暫無最近更新', en: 'No recent updates yet' },
  'assessmentsList.typeCommunication': { zh: '沟通评估', 'zh-TW': '溝通評估', en: 'Communication Assessment' },
  'assessmentsList.typeProgramming': { zh: '编程评估', 'zh-TW': '程式設計評估', en: 'Programming Assessment' },
  'assessmentsList.typeWriting': { zh: '写作评估', 'zh-TW': '寫作評估', en: 'Writing Assessment' },
  'assessmentsList.skillCoverageTitle': { zh: '覆盖的技能领域', 'zh-TW': '覆蓋的技能領域', en: 'Covered Skill Areas' },
  'assessmentsList.skillCoverageSubtitle': { zh: '当前评估类型与核心能力映射', 'zh-TW': '目前評估類型與核心能力映射', en: 'Mapping between assessment types and core competencies' },
  'assessmentsList.coverageCommunication': { zh: 'Communication', 'zh-TW': 'Communication', en: 'Communication' },
  'assessmentsList.coverageCommunicationDesc': { zh: '口头表达、即兴反应、逻辑组织', 'zh-TW': '口語表達、即興反應、邏輯組織', en: 'Oral expression, spontaneous response, logical organization' },
  'assessmentsList.coverageCoding': { zh: 'Coding Challenge', 'zh-TW': 'Coding Challenge', en: 'Coding Challenge' },
  'assessmentsList.coverageCodingDesc': { zh: '编程能力、算法思维、代码质量', 'zh-TW': '程式設計能力、演算法思維、程式碼品質', en: 'Programming ability, algorithmic thinking, code quality' },
  'assessmentsList.coverageWriting': { zh: 'Writing', 'zh-TW': 'Writing', en: 'Writing' },
  'assessmentsList.coverageWritingDesc': { zh: '书面表达、结构组织、语法', 'zh-TW': '書面表達、結構組織、語法', en: 'Written expression, structure, grammar' },
  'assess.dataAnalysis': { zh: '数据分析', 'zh-TW': '資料分析', en: 'Data Analysis' },
  'assess.problemSolving': { zh: '问题解决 / 案例分析', 'zh-TW': '問題解決 / 案例分析', en: 'Problem Solving / Case Study' },
  'assess.presentation': { zh: '演示 / 路演', 'zh-TW': '演示 / 簡報', en: 'Presentation / Pitch' },
  'assessmentsList.dataAnalysisDesc': { zh: '数据集分析与洞察', 'zh-TW': '資料集分析與洞察', en: 'Dataset analysis and insights' },
  'assessmentsList.problemSolvingDesc': { zh: '真实场景拆解与推理', 'zh-TW': '真實情境拆解與推理', en: 'Real-world case breakdown and reasoning' },
  'assessmentsList.presentationDesc': { zh: '结构化表达与说服展示', 'zh-TW': '結構化表達與說服展示', en: 'Structured delivery and persuasive presentation' },
  'assessmentsList.time20_35': { zh: '20-35 分钟', 'zh-TW': '20-35 分鐘', en: '20-35 minutes' },
  'assessmentsList.time20_30': { zh: '20-30 分钟', 'zh-TW': '20-30 分鐘', en: '20-30 minutes' },
  'assessmentsList.time8_10': { zh: '8-10 分钟', 'zh-TW': '8-10 分鐘', en: '8-10 minutes' },
  'assessmentsList.datasetInterpretation': { zh: '数据集解读', 'zh-TW': '資料集解讀', en: 'Dataset interpretation' },
  'assessmentsList.visualizationRecommendation': { zh: '可视化建议', 'zh-TW': '視覺化建議', en: 'Visualization recommendation' },
  'assessmentsList.aiInsightScoring': { zh: 'AI 洞察评分', 'zh-TW': 'AI 洞察評分', en: 'AI insight scoring' },
  'assessmentsList.caseAnalysis': { zh: '案例分析', 'zh-TW': '案例分析', en: 'Case analysis' },
  'assessmentsList.structuredThinking': { zh: '结构化思维', 'zh-TW': '結構化思維', en: 'Structured thinking' },
  'assessmentsList.multiStepReasoning': { zh: '多步骤推理', 'zh-TW': '多步驟推理', en: 'Multi-step reasoning' },
  'assessmentsList.structuredPresentation': { zh: '结构化演示', 'zh-TW': '結構化演示', en: 'Structured presentation' },
  'assessmentsList.persuasionScoring': { zh: '说服力分析', 'zh-TW': '說服力分析', en: 'Persuasion scoring' },
  'assessmentsList.visualAidRecommendation': { zh: '视觉辅助建议', 'zh-TW': '視覺輔助建議', en: 'Visual aid recommendations' },
  'assessmentsList.comingSoon': { zh: '即将上线', 'zh-TW': '即將上線', en: 'Coming Soon' },
  'assessmentsList.comingSoonHint': { zh: '该评估类型正在设计中，暂不可开始。', 'zh-TW': '此評估類型正在設計中，暫時無法開始。', en: 'This assessment type is in design and not yet available.' },
  'assessmentsList.actionDebounced': { zh: '操作过快，请稍候再试。', 'zh-TW': '操作過快，請稍候再試。', en: 'Action is too fast. Please wait a moment.' },
  'assessmentsList.idempotentReplayHint': { zh: '检测到重复提交，已返回上次结果。', 'zh-TW': '偵測到重複提交，已返回上次結果。', en: 'Duplicate submission detected. Returned the previous result.' },
  'assessmentsList.skillSyncQueuedHint': { zh: '技能更新已加入补偿队列，将自动完成同步。', 'zh-TW': '技能更新已加入補償佇列，將自動完成同步。', en: 'Skill update has been queued for automatic compensation sync.' },

  // 职位匹配页
  'jobs.pageTitle': { zh: '职位匹配', 'zh-TW': '職位匹配', en: 'Job Matching' },
  'jobs.pageSubtitle': { zh: '查看你的技能与不同职业路径的匹配度', 'zh-TW': '查看你的技能與不同職業路徑的匹配度', en: 'See how your skills match with different career paths' },
  'jobs.yourBestMatches': { zh: '🎯 最佳匹配', 'zh-TW': '🎯 最佳匹配', en: '🎯 Your Best Matches' },
  'jobs.analyzing': { zh: '正在分析你的技能...', 'zh-TW': '正在分析你的技能...', en: 'Analyzing your skills...' },
  'jobs.bestMatch': { zh: '⭐ 最佳匹配', 'zh-TW': '⭐ 最佳匹配', en: '⭐ Best Match' },
  'jobs.ready': { zh: '就绪', 'zh-TW': '就緒', en: 'ready' },
  'jobs.skillsMet': { zh: '项技能达标', 'zh-TW': '項技能達標', en: 'skills met' },
  'jobs.allRoles': { zh: '📋 所有角色', 'zh-TW': '📋 所有角色', en: '📋 All Roles' },
  'jobs.loadingRoles': { zh: '加载角色中...', 'zh-TW': '載入角色中...', en: 'Loading roles...' },
  'jobs.role': { zh: '角色', 'zh-TW': '角色', en: 'Role' },
  'jobs.readiness': { zh: '就绪度', 'zh-TW': '就緒度', en: 'Readiness' },
  'jobs.skills': { zh: '技能', 'zh-TW': '技能', en: 'Skills' },
  'jobs.status': { zh: '状态', 'zh-TW': '狀態', en: 'Status' },
  'jobs.skillGaps': { zh: '技能差距', 'zh-TW': '技能差距', en: 'Skill Gaps' },
  'jobs.action': { zh: '操作', 'zh-TW': '操作', en: 'Action' },
  'jobs.viewDetails': { zh: '查看详情', 'zh-TW': '查看詳情', en: 'View Details' },
  'jobs.readyLabel': { zh: '就绪', 'zh-TW': '就緒', en: 'Ready' },
  'jobs.almostReady': { zh: '接近就绪', 'zh-TW': '接近就緒', en: 'Almost Ready' },
  'jobs.inProgress': { zh: '进行中', 'zh-TW': '進行中', en: 'In Progress' },
  'jobs.allMet': { zh: '✓ 全部达标', 'zh-TW': '✓ 全部達標', en: '✓ All met' },
  'jobs.more': { zh: '更多', 'zh-TW': '更多', en: 'more' },
  'jobs.readyForRole': { zh: '适合该职位的就绪度', 'zh-TW': '適合該職位的就緒度', en: 'Ready for this role' },
  'jobs.skillsBreakdown': { zh: '技能明细', 'zh-TW': '技能明細', en: 'Skills Breakdown' },
  'jobs.skillsMetLabel': { zh: '技能达标', 'zh-TW': '技能達標', en: 'Skills Met' },
  'jobs.skillComparison': { zh: '您与该岗位的技能对比', 'zh-TW': '您與該崗位的技能對比', en: 'Your skills vs. this role' },
  'jobs.skillName': { zh: '技能', 'zh-TW': '技能', en: 'Skill' },
  'jobs.requiredLevel': { zh: '要求等级', 'zh-TW': '要求等級', en: 'Required' },
  'jobs.currentLevel': { zh: '当前等级', 'zh-TW': '當前等級', en: 'Yours' },
  'jobs.meet': { zh: '达标', 'zh-TW': '達標', en: 'Meet' },
  'jobs.needsStrengthening': { zh: '需加强', 'zh-TW': '需加強', en: 'Needs strengthening' },
  'jobs.missingProof': { zh: '缺证据', 'zh-TW': '缺證據', en: 'Missing proof' },
  'jobs.skillsNeeded': { zh: '待提升技能', 'zh-TW': '待提升技能', en: 'Skills Needed' },
  'jobs.recommendedActions': { zh: '🎯 推荐行动', 'zh-TW': '🎯 推薦行動', en: '🎯 Recommended Actions' },
  'jobs.uploadOrAssess': { zh: '上传证据或参加评估', 'zh-TW': '上傳證據或參加評估', en: 'Upload evidence or take an assessment' },
  'jobs.addEvidence': { zh: '添加证据', 'zh-TW': '添加證據', en: 'Add Evidence' },
  'jobs.close': { zh: '关闭', 'zh-TW': '關閉', en: 'Close' },
  'jobs.viewMySkills': { zh: '查看我的技能', 'zh-TW': '查看我的技能', en: 'View My Skills' },
  'jobs.noRolesYet': { zh: '暂无匹配数据', 'zh-TW': '暫無匹配資料', en: 'No matching data yet' },
  'jobs.uploadFirst': { zh: '请先上传文档并运行 AI 评估，然后系统会自动计算你与各职位的匹配度。', 'zh-TW': '請先上傳文件並執行 AI 評估，系統會自動計算你與各職位的匹配度。', en: 'Upload a document and run an AI assessment first. The system will then calculate your readiness for each role.' },

  // 通用
  'common.loading': { zh: '加载中...', 'zh-TW': '載入中...', en: 'Loading...' },
  'common.error': { zh: '错误', 'zh-TW': '錯誤', en: 'Error' },
  'common.success': { zh: '成功', 'zh-TW': '成功', en: 'Success' },
  'common.save': { zh: '保存', 'zh-TW': '儲存', en: 'Save' },
  'common.cancel': { zh: '取消', 'zh-TW': '取消', en: 'Cancel' },
  'common.confirm': { zh: '确认', 'zh-TW': '確認', en: 'Confirm' },
  'common.close': { zh: '关闭', 'zh-TW': '關閉', en: 'Close' },
  'common.back': { zh: '返回', 'zh-TW': '返回', en: 'Back' },
  'common.level': { zh: '等级', 'zh-TW': '等級', en: 'Level' },
  'common.score': { zh: '分数', 'zh-TW': '分數', en: 'Score' },
  'common.overall': { zh: '总分', 'zh-TW': '總分', en: 'Overall' },
  'common.viewMore': { zh: '查看更多', 'zh-TW': '查看更多', en: 'View More' },
  'common.noData': { zh: '暂无数据', 'zh-TW': '暫無資料', en: 'No data' },
  'common.retry': { zh: '重试', 'zh-TW': '重試', en: 'Retry' },
  'common.login': { zh: '登录', 'zh-TW': '登入', en: 'Login' },
  'common.delete': { zh: '删除', 'zh-TW': '刪除', en: 'Delete' },
  'common.deleting': { zh: '删除中...', 'zh-TW': '刪除中...', en: 'Deleting...' },
  'common.confirmDelete': { zh: '确认删除', 'zh-TW': '確認刪除', en: 'Confirm Delete' },
  'common.networkError': { zh: '网络错误，请重试', 'zh-TW': '網路錯誤，請重試', en: 'Network error, please try again' },
  'common.loadFailed': { zh: '加载失败', 'zh-TW': '載入失敗', en: 'Load Failed' },
  'common.retryAfterLogin': { zh: '后重试。', 'zh-TW': '後重試。', en: 'and try again.' },
  'common.loadMore': { zh: '加载更多', 'zh-TW': '載入更多', en: 'Load more' },
  'common.none': { zh: '无', 'zh-TW': '無', en: 'None' },
  'common.unknown': { zh: '未知', 'zh-TW': '未知', en: 'Unknown' },
  'common.page': { zh: '页', 'zh-TW': '頁', en: '' },
  'common.pagePrefix': { zh: '第', 'zh-TW': '第', en: 'Page ' },
  'common.chars': { zh: '字符数:', 'zh-TW': '字元數:', en: 'Characters:' },
  'common.collapse': { zh: '点击收起', 'zh-TW': '點擊收起', en: 'Click to collapse' },
  'common.share': { zh: '分享', 'zh-TW': '分享', en: 'Share' },

  // 上传页面
  'upload.title': { zh: '上传证据文档', 'zh-TW': '上傳證據文件', en: 'Upload Evidence Document' },
  'upload.subtitle': { zh: '上传你的作品、报告、代码或其他能证明技能的文件', 'zh-TW': '上傳你的作品、報告、程式碼或其他能證明技能的文件', en: 'Upload your work, reports, code, or other files that demonstrate your skills' },
  'upload.success': { zh: '上传成功！', 'zh-TW': '上傳成功！', en: 'Upload Successful!' },
  'upload.processed': { zh: '已处理，生成了', 'zh-TW': '已處理，生成了', en: 'Processed, generated' },
  'upload.chunks': { zh: '个证据片段', 'zh-TW': '個證據片段', en: 'evidence chunks' },
  'upload.viewDetails': { zh: '查看证据详情', 'zh-TW': '查看證據詳情', en: 'View Evidence Details' },
  'upload.backToDashboard': { zh: '返回仪表盘', 'zh-TW': '返回儀表板', en: 'Back to Dashboard' },
  'upload.failed': { zh: '上传失败', 'zh-TW': '上傳失敗', en: 'Upload Failed' },
  'upload.rejected': { zh: '请求被拒绝：', 'zh-TW': '請求被拒絕：', en: 'Request rejected: ' },
  'upload.nextStep': { zh: '下一步：', 'zh-TW': '下一步：', en: 'Next step:' },
  'upload.clickToChange': { zh: '点击更换文件', 'zh-TW': '點擊更換文件', en: 'Click to change file' },
  'upload.dropHere': { zh: '拖放文件到此处', 'zh-TW': '拖放文件到此處', en: 'Drop file here' },
  'upload.orClick': { zh: '或点击选择文件', 'zh-TW': '或點擊選擇文件', en: 'or click to select file' },
  'upload.consentTitle': { zh: '🔒 数据使用授权（必填）', 'zh-TW': '🔒 資料使用授權（必填）', en: '🔒 Data Usage Authorization (Required)' },
  'upload.consentDesc': { zh: '根据 Protocol 9（Consent），上传前必须声明用途和范围。你可随时撤回授权并删除所有数据。', 'zh-TW': '根據 Protocol 9（Consent），上傳前必須聲明用途和範圍。你可隨時撤回授權並刪除所有資料。', en: 'Per Protocol 9 (Consent), you must declare purpose and scope before uploading. You can revoke authorization and delete all data at any time.' },
  'upload.purpose': { zh: '使用目的 (Purpose)', 'zh-TW': '使用目的 (Purpose)', en: 'Purpose' },
  'upload.scope': { zh: '处理范围 (Scope)', 'zh-TW': '處理範圍 (Scope)', en: 'Scope' },
  'upload.consentGranted': { zh: '已授权：用途「', 'zh-TW': '已授權：用途「', en: 'Authorized: Purpose "' },
  'upload.consentScope': { zh: '」，范围「', 'zh-TW': '」，範圍「', en: '", Scope "' },
  'upload.consentRevoke': { zh: '」。你可随时在隐私管理页撤回授权。', 'zh-TW': '」。你可隨時在隱私管理頁撤回授權。', en: '". You can revoke authorization anytime in the privacy settings.' },
  'upload.processing': { zh: '处理中...', 'zh-TW': '處理中...', en: 'Processing...' },
  'upload.button': { zh: '上传文档', 'zh-TW': '上傳文件', en: 'Upload Document' },
  'upload.tipsTitle': { zh: '💡 上传建议', 'zh-TW': '💡 上傳建議', en: '💡 Upload Tips' },
  'upload.tip1': { zh: '✓ 上传能展示具体技能应用的作品或报告', 'zh-TW': '✓ 上傳能展示具體技能應用的作品或報告', en: '✓ Upload work or reports that demonstrate specific skill applications' },
  'upload.tip2': { zh: '✓ 代码文件请确保有注释说明', 'zh-TW': '✓ 程式碼文件請確保有注釋說明', en: '✓ Ensure code files have comments and explanations' },
  'upload.tip3': { zh: '✓ 图片自动 OCR 提取文字，音视频自动转录', 'zh-TW': '✓ 圖片自動 OCR 提取文字，音視頻自動轉錄', en: '✓ Images auto-OCR extracted, audio/video auto-transcribed' },
  'upload.tip4': { zh: '✓ 建议单个文件不超过 20MB', 'zh-TW': '✓ 建議單個文件不超過 20MB', en: '✓ Recommended file size: under 20MB' },
  'upload.purposeSkillAssess': { zh: '技能评估 (Skill Assessment)', 'zh-TW': '技能評估 (Skill Assessment)', en: 'Skill Assessment' },
  'upload.purposeSkillAssessDesc': { zh: '用于证明和评估具体技能', 'zh-TW': '用於證明和評估具體技能', en: 'To demonstrate and assess specific skills' },
  'upload.purposeRoleAlign': { zh: '岗位匹配 (Role Alignment)', 'zh-TW': '職位匹配 (Role Alignment)', en: 'Role Alignment' },
  'upload.purposeRoleAlignDesc': { zh: '用于评估与目标岗位的匹配度', 'zh-TW': '用於評估與目標職位的匹配度', en: 'To assess alignment with target role' },
  'upload.purposePortfolio': { zh: '作品集 (Portfolio)', 'zh-TW': '作品集 (Portfolio)', en: 'Portfolio' },
  'upload.purposePortfolioDesc': { zh: '作为个人作品集的一部分', 'zh-TW': '作為個人作品集的一部分', en: 'As part of a personal portfolio' },
  'upload.scopeFull': { zh: '完整处理 (Full)', 'zh-TW': '完整處理 (Full)', en: 'Full Processing' },
  'upload.scopeFullDesc': { zh: '处理全文内容', 'zh-TW': '處理全文內容', en: 'Process full content' },
  'upload.scopeExcerpt': { zh: '摘要 (Excerpt)', 'zh-TW': '摘要 (Excerpt)', en: 'Excerpt' },
  'upload.scopeExcerptDesc': { zh: '仅处理关键片段', 'zh-TW': '僅處理關鍵片段', en: 'Process key excerpts only' },
  'upload.scopeSummary': { zh: '概要 (Summary)', 'zh-TW': '概要 (Summary)', en: 'Summary' },
  'upload.scopeSummaryDesc': { zh: '仅生成概要', 'zh-TW': '僅生成概要', en: 'Generate summary only' },
  'upload.typeDoc': { zh: '文档', 'zh-TW': '文件', en: 'Document' },
  'upload.typeTable': { zh: '表格', 'zh-TW': '表格', en: 'Table' },
  'upload.typeImage': { zh: '图片', 'zh-TW': '圖片', en: 'Image' },
  'upload.typeMedia': { zh: '音视频', 'zh-TW': '音視頻', en: 'Audio/Video' },
  'upload.typeCode': { zh: '代码', 'zh-TW': '程式碼', en: 'Code' },
  'upload.pageSubtitle': { zh: '添加文档、项目或录音以建立你的技能档案', 'zh-TW': '添加文件、專案或錄音以建立你的技能檔案', en: 'Add documents, projects, or recordings to build your skill profile' },
  'upload.filesProcessedSuccess': { zh: '个文件已成功处理。', 'zh-TW': '個文件已成功處理。', en: 'file(s) processed successfully.' },
  'upload.autoAssessHint': { zh: '系统将根据文档自动评估技能，约 1–2 分钟内可在首页看到更新。', 'zh-TW': '系統將根據文件自動評估技能，約 1–2 分鐘內可在首頁看到更新。', en: 'Skills will be auto-assessed from your documents; updates will appear on the dashboard in 1–2 minutes.' },
  'upload.autoAssessDone': { zh: '已为 {n} 项技能完成自动评估', 'zh-TW': '已為 {n} 項技能完成自動評估', en: 'Auto-assessed {n} skills.' },
  'upload.autoAssessNoUpdate': { zh: '自动评估未更新技能，请确认文档已解析完成或稍后在技能页手动评估。', 'zh-TW': '自動評估未更新技能，請確認文件已解析完成或稍後在技能頁手動評估。', en: 'Auto-assess did not update skills. Confirm documents are parsed or assess manually on the Skills page.' },
  'upload.sectionsExtracted': { zh: '个证据片段已提取', 'zh-TW': '個證據片段已提取', en: 'evidence sections extracted' },
  'upload.selectFiles': { zh: '📤 选择文件', 'zh-TW': '📤 選擇文件', en: '📤 Select Files' },
  'upload.dropOrBrowse': { zh: '将文件拖放到此处或点击选择', 'zh-TW': '將文件拖放到此處或點擊選擇', en: 'Drop files here or click to browse' },
  'upload.maxFileSize': { zh: '单个文件最大 20MB', 'zh-TW': '單個文件最大 20MB', en: 'Maximum 20MB per file' },
  'upload.supportedFormats': { zh: '支持格式：', 'zh-TW': '支援格式：', en: 'Supported formats:' },
  'upload.demoRouteTitle': { zh: '👋 新手示范路线', 'zh-TW': '👋 新手示範路線', en: '👋 Quick Start Route' },
  'upload.demoRouteDesc': { zh: '不确定从哪里开始？按下面 4 步走一遍，10 分钟内就能看到完整结果。', 'zh-TW': '不確定從哪裡開始？按下面 4 步走一遍，10 分鐘內就能看到完整結果。', en: 'Not sure where to start? Follow this 4-step route and get full results quickly.' },
  'upload.nextViewSkills': { zh: '下一步：查看技能档案', 'zh-TW': '下一步：查看技能檔案', en: 'Next: View Skills Profile' },
  'upload.nextViewJobs': { zh: '下一步：查看职位匹配', 'zh-TW': '下一步：查看職位匹配', en: 'Next: View Job Matching' },
  'upload.selectedFiles': { zh: '已选文件', 'zh-TW': '已選文件', en: 'Selected files' },
  'upload.consentCheckbox': { zh: '我同意将这些文件用于技能评估', 'zh-TW': '我同意將這些文件用於技能評估', en: 'I consent to processing these files for skill assessment' },
  'upload.consentWithdraw': { zh: '你可随时在 设置 → 隐私与数据 中撤回同意并删除数据。', 'zh-TW': '你可隨時在 設定 → 隱私與資料 中撤回同意並刪除資料。', en: 'You can withdraw consent and delete your data at any time from Settings → Privacy.' },
  'upload.uploadFiles': { zh: '📤 上传文件', 'zh-TW': '📤 上傳文件', en: '📤 Upload Files' },
  'upload.uploadNFiles': { zh: '📤 上传 {n} 个文件', 'zh-TW': '📤 上傳 {n} 個文件', en: '📤 Upload {n} File(s)' },
  'upload.tipsTitleResults': { zh: '💡 获得更好结果的建议', 'zh-TW': '💡 獲得更好結果的建議', en: '💡 Tips for Better Results' },
  'upload.tip1page': { zh: '上传能展示你工作的完整项目或报告', 'zh-TW': '上傳能展示你工作的完整專案或報告', en: 'Upload complete projects or reports that show your work' },
  'upload.tip2page': { zh: '代码文件请附带注释说明你的思路', 'zh-TW': '程式碼文件請附帶注釋說明你的思路', en: 'Include code files with comments explaining your approach' },
  'upload.tip3page': { zh: '视频演示将自动转写', 'zh-TW': '影片簡報將自動轉寫', en: 'Video presentations will be transcribed automatically' },
  'upload.tip4page': { zh: '含文字的图片（证书、图表）将经 OCR 处理', 'zh-TW': '含文字的圖片（證書、圖表）將經 OCR 處理', en: 'Images with text (certificates, diagrams) will be processed via OCR' },
  'upload.privacyCardTitle': { zh: '🔒 隐私', 'zh-TW': '🔒 隱私', en: '🔒 Privacy' },
  'upload.privacyCardDesc': { zh: '你的文件会被安全处理，仅用于技能评估。你始终拥有数据的完全控制权。', 'zh-TW': '你的文件會被安全處理，僅用於技能評估。你始終擁有資料的完全控制權。', en: 'Your files are processed securely and only used for skill assessment. You maintain full control over your data.' },
  'upload.managePrivacy': { zh: '🔒 管理隐私设置', 'zh-TW': '🔒 管理隱私設定', en: '🔒 Manage Privacy Settings' },
  'upload.loginRequired': { zh: '请先登录后再上传文档。', 'zh-TW': '請先登入後再上傳文件。', en: 'Please log in to upload documents.' },
  'upload.embedding': { zh: '正在生成向量...', 'zh-TW': '正在生成向量...', en: 'Generating embeddings...' },
  'upload.assessing': { zh: 'AI 评估技能中', 'zh-TW': 'AI 評估技能中', en: 'AI assessing skills' },
  'upload.done': { zh: '完成！', 'zh-TW': '完成！', en: 'Complete!' },
  'upload.unsupportedType': { zh: '不支持该文件格式，请选择支持的格式。', 'zh-TW': '不支援該檔案格式，請選擇支援的格式。', en: 'Unsupported file type. Please choose a supported format.' },
  'admin.audit': { zh: '审计日志', 'zh-TW': '審計日誌', en: 'Audit Log' },
  'admin.jobs': { zh: '后台任务', 'zh-TW': '後台任務', en: 'Background Jobs' },
  'error.somethingWrong': { zh: '出错了', 'zh-TW': '出錯了', en: 'Something went wrong' },
  'error.tryAgain': { zh: '重试', 'zh-TW': '重試', en: 'Try again' },
  'dashboard.errorFallback': { zh: '仪表盘加载失败，请重试或返回首页', 'zh-TW': '儀表盤載入失敗，請重試或返回首頁', en: 'Dashboard failed to load. Try again or go home.' },
  'error.backToDashboard': { zh: '返回仪表盘', 'zh-TW': '返回儀表板', en: 'Back to Dashboard' },
  'error.notFound': { zh: '页面未找到', 'zh-TW': '頁面未找到', en: 'Page not found' },
  'error.notFoundHint': { zh: '您访问的页面不存在或已移动。', 'zh-TW': '您訪問的頁面不存在或已移動。', en: 'The page you are looking for does not exist or has been moved.' },

  // 隐私设置页
  'privacy.dataOverview': { zh: '📊 数据概览', 'zh-TW': '📊 資料概覽', en: '📊 Data Overview' },
  'privacy.activeConsents': { zh: '活跃授权', 'zh-TW': '活躍授權', en: 'Active Consents' },
  'privacy.revoked': { zh: '已撤回', 'zh-TW': '已撤回', en: 'Revoked' },
  'privacy.allRecords': { zh: '全部记录', 'zh-TW': '全部記錄', en: 'All Records' },
  'privacy.authorizedDocs': { zh: '📄 已授权文档', 'zh-TW': '📄 已授權文件', en: '📄 Authorized Documents' },
  'privacy.revokeAll': { zh: '🗑️ 撤回全部授权', 'zh-TW': '🗑️ 撤回全部授權', en: '🗑️ Revoke All Authorizations' },
  'privacy.loading': { zh: '加载中...', 'zh-TW': '載入中...', en: 'Loading...' },
  'privacy.filename': { zh: '文件名', 'zh-TW': '檔案名', en: 'Filename' },
  'privacy.purpose': { zh: '用途 (Purpose)', 'zh-TW': '用途 (Purpose)', en: 'Purpose' },
  'privacy.scope': { zh: '范围 (Scope)', 'zh-TW': '範圍 (Scope)', en: 'Scope' },
  'privacy.uploadTime': { zh: '上传时间', 'zh-TW': '上傳時間', en: 'Upload Time' },
  'privacy.actions': { zh: '操作', 'zh-TW': '操作', en: 'Actions' },
  'privacy.revokeDelete': { zh: '🗑️ 撤回 & 删除', 'zh-TW': '🗑️ 撤回 & 刪除', en: '🗑️ Revoke & Delete' },
  'privacy.noActive': { zh: '没有活跃授权', 'zh-TW': '沒有活躍授權', en: 'No active authorizations' },
  'privacy.noActiveDesc': { zh: '你还没有上传任何文档，或所有授权已撤回', 'zh-TW': '你還沒有上傳任何文件，或所有授權已撤回', en: 'You have not uploaded any documents, or all authorizations have been revoked' },
  'privacy.revokedRecords': { zh: '📋 已撤回记录（审计留存）', 'zh-TW': '📋 已撤回記錄（審計留存）', en: '📋 Revoked Records (Audit Retention)' },
  'privacy.revokedAt': { zh: '撤回时间', 'zh-TW': '撤回時間', en: 'Revoked At' },
  'privacy.reason': { zh: '原因', 'zh-TW': '原因', en: 'Reason' },
  'privacy.revokedSuccess': { zh: '已撤回授权并永久删除所有相关数据。审计 ID：', 'zh-TW': '已撤回授權並永久刪除所有相關資料。審計 ID：', en: 'Authorization revoked and all related data permanently deleted. Audit ID: ' },
  'privacy.revokeFailed': { zh: '撤回失败', 'zh-TW': '撤回失敗', en: 'Revocation Failed' },
  'privacy.revokeConfirm': { zh: '确定要撤回所有文档的授权并永久删除所有数据吗？此操作不可撤销。', 'zh-TW': '確定要撤回所有文件的授權並永久刪除所有資料嗎？此操作不可撤銷。', en: 'Are you sure you want to revoke all document authorizations and permanently delete all data? This action cannot be undone.' },

  // 变更日志页
  'changelog.skillChange': { zh: '技能状态变化', 'zh-TW': '技能狀態變化', en: 'Skill Status Change' },
  'changelog.roleChange': { zh: '角色就绪度变化', 'zh-TW': '角色就緒度變化', en: 'Role Readiness Change' },
  'changelog.consentRevoke': { zh: '同意撤回', 'zh-TW': '同意撤回', en: 'Consent Revoked' },
  'changelog.docDelete': { zh: '文档删除', 'zh-TW': '文件刪除', en: 'Document Deleted' },
  'changelog.actionUpdate': { zh: '动作推荐更新', 'zh-TW': '動作推薦更新', en: 'Action Recommendation Update' },
  'changelog.title': { zh: '可解释变更记录：What / Why / When 与证据指针', 'zh-TW': '可解釋變更記錄：What / Why / When 與證據指針', en: 'Explainable Change Log: What / Why / When with Evidence Pointers' },
  'changelog.refresh': { zh: '↻ 刷新', 'zh-TW': '↻ 重新整理', en: '↻ Refresh' },
  'changelog.loading': { zh: '加载中...', 'zh-TW': '載入中...', en: 'Loading...' },
  'changelog.loadFailed': { zh: '加载失败', 'zh-TW': '載入失敗', en: 'Load Failed' },
  'changelog.loginRetry': { zh: '后重试。', 'zh-TW': '後重試。', en: 'and try again.' },
  'changelog.code': { zh: '代码:', 'zh-TW': '代碼:', en: 'Code:' },
  'changelog.noEvents': { zh: '暂无变更事件', 'zh-TW': '暫無變更事件', en: 'No change events' },
  'changelog.noEventsDesc': { zh: '上传文档、运行技能评估或角色就绪度后会产生变更记录。', 'zh-TW': '上傳文件、執行技能評估或角色就緒度後會產生變更記錄。', en: 'Change records are generated after uploading documents, running skill assessments, or role readiness evaluations.' },
  'changelog.before': { zh: '变更前:', 'zh-TW': '變更前:', en: 'Before:' },
  'changelog.after': { zh: '变更后:', 'zh-TW': '變更後:', en: 'After:' },
  'changelog.why': { zh: 'Why (证据/规则):', 'zh-TW': 'Why (證據/規則):', en: 'Why (Evidence/Rule):' },
  'changelog.collapse': { zh: '▲ 收起', 'zh-TW': '▲ 收起', en: '▲ Collapse' },
  'changelog.expand': { zh: '▼ 展开详情', 'zh-TW': '▼ 展開詳情', en: '▼ Expand Details' },
  'changelog.loadMore': { zh: '加载更多', 'zh-TW': '載入更多', en: 'Load more' },
  'changelog.navLabel': { zh: '变更日志', 'zh-TW': '變更日誌', en: 'Change Log' },
  'admin.changeLog': { zh: '变更日志', 'zh-TW': '變更日誌', en: 'Change Log' },
  'admin.changelog.subtitle': { zh: '治理审计：按 subject_id / event_type / request_id 过滤', 'zh-TW': '治理審計：按 subject_id / event_type / request_id 過濾', en: 'Governance audit: filter by subject_id / event_type / request_id' },
  'admin.changelog.search': { zh: '查询', 'zh-TW': '查詢', en: 'Search' },
  'admin.changelog.noEventsFilterHint': { zh: '尝试放宽筛选条件后重试。', 'zh-TW': '嘗試放寬篩選條件後重試。', en: 'Try broadening your filter criteria.' },
  'admin.changelog.expandJson': { zh: '▼ 展开 JSON', 'zh-TW': '▼ 展開 JSON', en: '▼ Expand JSON' },
  'admin.changelog.eventSkillChanged': { zh: '技能变化', 'zh-TW': '技能變化', en: 'Skill Changed' },
  'admin.changelog.eventRoleReadiness': { zh: '角色就绪度', 'zh-TW': '角色就緒度', en: 'Role Readiness' },
  'admin.changelog.eventConsentWithdrawn': { zh: '同意撤回', 'zh-TW': '同意撤回', en: 'Consent Withdrawn' },
  'admin.changelog.eventDocDeleted': { zh: '文档删除', 'zh-TW': '文件刪除', en: 'Document Deleted' },
  'admin.changelog.eventActionsChanged': { zh: '动作更新', 'zh-TW': '動作更新', en: 'Actions Updated' },
  'nav.hint.dashboard': { zh: '总览你的文档、技能与匹配结果', 'zh-TW': '總覽你的文件、技能與匹配結果', en: 'Overview of your documents, skills, and matches' },
  'nav.hint.upload': { zh: '上传任意技能证据文件，系统自动解析', 'zh-TW': '上傳任意技能證據文件，系統自動解析', en: 'Upload skill evidence files for automatic parsing' },
  'nav.hint.skills': { zh: '查看每项技能的证据与等级状态', 'zh-TW': '查看每項技能的證據與等級狀態', en: 'Review evidence and level status for each skill' },
  'nav.hint.jobs': { zh: '查看岗位匹配与能力差距建议', 'zh-TW': '查看職位匹配與能力差距建議', en: 'See role matches and capability gap guidance' },
  'nav.hint.assessments': { zh: '完成互动评估增强技能可信度', 'zh-TW': '完成互動評估增強技能可信度', en: 'Complete interactive assessments to strengthen evidence' },
  'nav.hint.changeLog': { zh: '追踪技能和匹配结果的变化原因', 'zh-TW': '追蹤技能和匹配結果的變化原因', en: 'Track why your skill and readiness results changed' },
  'nav.hint.settings': { zh: '管理主题、语言和个人偏好', 'zh-TW': '管理主題、語言和個人偏好', en: 'Manage theme, language, and personal preferences' },
  'nav.hint.privacy': { zh: '查看授权记录并撤回数据使用权限', 'zh-TW': '查看授權記錄並撤回資料使用權限', en: 'Review consents and revoke data permissions' },

  // 导出页面
  'export.back': { zh: '← 返回 Skills Profile', 'zh-TW': '← 返回 Skills Profile', en: '← Back to Skills Profile' },
  'export.title': { zh: '导出技能声明', 'zh-TW': '匯出技能聲明', en: 'Export Skills Statement' },
  'export.print': { zh: '🖨️ 打印 / 导出 PDF', 'zh-TW': '🖨️ 列印 / 匯出 PDF', en: '🖨️ Print / Export PDF' },
  'export.certificateNote': { zh: '可分享的技能评估证书：打印或另存为 PDF 后可放入作品集或求职材料。', 'zh-TW': '可分享的技能評估證書：列印或另存為 PDF 後可放入作品集或求職材料。', en: 'Shareable skills assessment certificate: print or save as PDF for your portfolio or job applications.' },
  'export.verifyLabel': { zh: '验证此声明', 'zh-TW': '驗證此聲明', en: 'Verify this statement' },
  'export.verifyLink': { zh: '验证链接', 'zh-TW': '驗證連結', en: 'Verification link' },
  'export.verifyThisStatement': { zh: '验证此声明', 'zh-TW': '驗證此聲明', en: 'Verify this statement' },
  'export.verifyTitle': { zh: '验证声明', 'zh-TW': '驗證聲明', en: 'Verify Statement' },
  'export.verifyChecking': { zh: '验证中…', 'zh-TW': '驗證中…', en: 'Checking…' },
  'export.verifyValid': { zh: '声明有效', 'zh-TW': '聲明有效', en: 'Valid statement' },
  'export.verifyIssuedBy': { zh: '本声明由 SkillSight 于以下日期签发', 'zh-TW': '本聲明由 SkillSight 於以下日期簽發', en: 'This statement was issued by SkillSight on' },
  'export.verifyExpired': { zh: '声明已过期，请重新生成。', 'zh-TW': '聲明已過期，請重新生成。', en: 'Statement expired, please regenerate.' },
  'export.verifyInvalid': { zh: '验证码无效或已过期。', 'zh-TW': '驗證碼無效或已過期。', en: 'Invalid or expired verification token.' },
  'export.verifyNoToken': { zh: '未提供验证码。', 'zh-TW': '未提供驗證碼。', en: 'No token provided.' },
  'export.verifyError': { zh: '验证请求失败。', 'zh-TW': '驗證請求失敗。', en: 'Verification request failed.' },
  'export.subjectId': { zh: '主体ID', 'zh-TW': '主體ID', en: 'Subject ID' },
  'export.backToDashboard': { zh: '返回仪表盘', 'zh-TW': '返回儀表板', en: 'Back to Dashboard' },
  'export.generating': { zh: '生成声明中...', 'zh-TW': '生成聲明中...', en: 'Generating statement...' },
  'export.loadFailed': { zh: '⚠ 加载失败', 'zh-TW': '⚠ 載入失敗', en: '⚠ Load Failed' },
  'export.loadFailedMsg': { zh: '请确保已登录并上传文档，然后重试。', 'zh-TW': '請確保已登入並上傳文件，然後重試。', en: 'Please ensure you are logged in and have uploaded documents, then try again.' },
  'export.notLoggedIn': { zh: '未登录', 'zh-TW': '未登入', en: 'Not logged in' },
  'export.failedToLoad': { zh: '加载失败', 'zh-TW': '載入失敗', en: 'Failed to load' },
  'export.skillsStatement': { zh: '技能声明', 'zh-TW': '技能聲明', en: 'Skills Statement' },
  'export.studentId': { zh: '学生 ID：', 'zh-TW': '學生 ID：', en: 'Student ID: ' },
  'export.generated': { zh: '生成时间：', 'zh-TW': '生成時間：', en: 'Generated: ' },
  'export.skillsAssessed': { zh: '已评估技能', 'zh-TW': '已評估技能', en: 'Skills Assessed' },
  'export.skillsDemonstrated': { zh: '已展示技能', 'zh-TW': '已展示技能', en: 'Skills Demonstrated' },
  'export.evidenceItems': { zh: '证据条数', 'zh-TW': '證據條數', en: 'Evidence Items' },
  'export.evidenceSources': { zh: '证据来源', 'zh-TW': '證據來源', en: 'Evidence Sources' },
  'export.filename': { zh: '文件名', 'zh-TW': '檔案名', en: 'Filename' },
  'export.consent': { zh: '授权', 'zh-TW': '授權', en: 'Consent' },
  'export.scope': { zh: '范围', 'zh-TW': '範圍', en: 'Scope' },
  'export.granted': { zh: '✓ 已授权', 'zh-TW': '✓ 已授權', en: '✓ Granted' },
  'export.demonstratedSkills': { zh: '已展示技能', 'zh-TW': '已展示技能', en: 'Demonstrated Skills' },
  'export.noSkillsDemonstrated': { zh: '暂无已展示技能', 'zh-TW': '暫無已展示技能', en: 'No skills demonstrated yet' },
  'export.noSkillsDemonstratedDesc': { zh: '上传并评估你的证据文档后将会显示。', 'zh-TW': '上傳並評估你的證據文件後將會顯示。', en: 'Upload and assess your evidence documents.' },
  'export.demonstrated': { zh: '✓ 已展示', 'zh-TW': '✓ 已展示', en: '✓ Demonstrated' },
  'export.mentioned': { zh: '○ 已提及', 'zh-TW': '○ 已提及', en: '○ Mentioned' },
  'export.evidence': { zh: '证据', 'zh-TW': '證據', en: 'Evidence' },

  // 文档详情页
  'doc.info': { zh: '文档信息', 'zh-TW': '文件資訊', en: 'Document Info' },
  'doc.notFound': { zh: '文档不存在或无法加载', 'zh-TW': '文件不存在或無法載入', en: 'Document not found or cannot be loaded' },
  'doc.type': { zh: '类型:', 'zh-TW': '類型:', en: 'Type:' },
  'doc.uploadTime': { zh: '上传时间:', 'zh-TW': '上傳時間:', en: 'Upload Time:' },
  'doc.processed': { zh: '已处理', 'zh-TW': '已處理', en: 'Processed' },
  'doc.skillAssess': { zh: '技能评估', 'zh-TW': '技能評估', en: 'Skill Assessment' },
  'doc.selectSkill': { zh: '选择技能后运行评估', 'zh-TW': '選擇技能後執行評估', en: 'Select a skill to run assessment' },
  'doc.selectSkillLabel': { zh: '选择要评估的技能', 'zh-TW': '選擇要評估的技能', en: 'Select skill to assess' },
  'doc.analyzing': { zh: '分析中...', 'zh-TW': '分析中...', en: 'Analyzing...' },
  'doc.skillMatch': { zh: '技能匹配', 'zh-TW': '技能匹配', en: 'Skill Match' },
  'doc.detectEvidence': { zh: '检测相关证据', 'zh-TW': '偵測相關證據', en: 'Detect relevant evidence' },
  'doc.assessing': { zh: '评估中...', 'zh-TW': '評估中...', en: 'Assessing...' },
  'doc.proficiencyAssess': { zh: '熟练度评估', 'zh-TW': '熟練度評估', en: 'Proficiency Assessment' },
  'doc.ruleBasedLevel': { zh: '规则判定等级', 'zh-TW': '規則判定等級', en: 'Rule-based level determination' },
  'doc.aiAssess': { zh: 'AI智能评估', 'zh-TW': 'AI智能評估', en: 'AI Smart Assessment' },
  'doc.deepAnalysis': { zh: '深度分析熟练度', 'zh-TW': '深度分析熟練度', en: 'Deep proficiency analysis' },
  'doc.verifying': { zh: '验证中...', 'zh-TW': '驗證中...', en: 'Verifying...' },
  'doc.capabilityVerify': { zh: '能力验证', 'zh-TW': '能力驗證', en: 'Capability Verification' },
  'doc.verifyApp': { zh: '验证实际应用', 'zh-TW': '驗證實際應用', en: 'Verify practical application' },
  'doc.skillMatchTitle': { zh: '🔍 技能匹配', 'zh-TW': '🔍 技能匹配', en: '🔍 Skill Match' },
  'doc.matched': { zh: '已匹配', 'zh-TW': '已匹配', en: 'Matched' },
  'doc.clickToDetect': { zh: '点击"技能匹配"按钮开始检测', 'zh-TW': '點擊「技能匹配」按鈕開始偵測', en: 'Click "Skill Match" button to start detection' },
  'doc.matchedTerms': { zh: '匹配术语：', 'zh-TW': '匹配術語：', en: 'Matched terms: ' },
  'doc.bestEvidence': { zh: '最佳证据：', 'zh-TW': '最佳證據：', en: 'Best evidence: ' },
  'doc.viewChunk': { zh: '查看片段', 'zh-TW': '查看片段', en: 'View Chunk' },
  'doc.proficiencyTitle': { zh: '📊 熟练度评估', 'zh-TW': '📊 熟練度評估', en: '📊 Proficiency Assessment' },
  'doc.clickToProficiency': { zh: '点击"熟练度评估"按钮开始评估', 'zh-TW': '點擊「熟練度評估」按鈕開始評估', en: 'Click "Proficiency Assessment" button to start' },
  'doc.assessReason': { zh: '评估理由：', 'zh-TW': '評估理由：', en: 'Assessment reason: ' },
  'doc.evidenceSource': { zh: '证据来源：', 'zh-TW': '證據來源：', en: 'Evidence source: ' },
  'doc.aiAssessTitle': { zh: '🤖 AI智能评估', 'zh-TW': '🤖 AI智能評估', en: '🤖 AI Smart Assessment' },
  'doc.matchCriteria': { zh: '匹配标准：', 'zh-TW': '匹配標準：', en: 'Match criteria: ' },
  'doc.analysisNote': { zh: '分析说明：', 'zh-TW': '分析說明：', en: 'Analysis note: ' },
  'doc.capabilityTitle': { zh: '✅ 能力验证', 'zh-TW': '✅ 能力驗證', en: '✅ Capability Verification' },
  'doc.onlyMentioned': { zh: '仅提及', 'zh-TW': '僅提及', en: 'Only Mentioned' },
  'doc.verifyNote': { zh: '验证说明：', 'zh-TW': '驗證說明：', en: 'Verification note: ' },
  'doc.remarks': { zh: '备注：', 'zh-TW': '備註：', en: 'Remarks: ' },
  'doc.roleMatch': { zh: '角色匹配', 'zh-TW': '角色匹配', en: 'Role Matching' },
  'doc.assessRoleReadiness': { zh: '评估职位就绪度', 'zh-TW': '評估職位就緒度', en: 'Assess role readiness' },
  'doc.selectRole': { zh: '选择目标角色', 'zh-TW': '選擇目標角色', en: 'Select target role' },
  'doc.assessReadiness': { zh: '📊 评估就绪度', 'zh-TW': '📊 評估就緒度', en: '📊 Assess Readiness' },
  'doc.getActions': { zh: '💡 获取行动建议', 'zh-TW': '💡 獲取行動建議', en: '💡 Get Action Recommendations' },
  'doc.generating': { zh: '生成中...', 'zh-TW': '生成中...', en: 'Generating...' },
  'doc.met': { zh: '达标', 'zh-TW': '達標', en: 'Met' },
  'doc.needsImprovement': { zh: '需加强', 'zh-TW': '需加強', en: 'Needs Improvement' },
  'doc.lackEvidence': { zh: '缺证据', 'zh-TW': '缺證據', en: 'Lacks Evidence' },
  'doc.actionTitle': { zh: '💡 行动建议', 'zh-TW': '💡 行動建議', en: '💡 Action Recommendations' },
  'doc.actionDoneHint': { zh: '建议上传与该技能相关的新证据，我们将重新评估。', 'zh-TW': '建議上傳與該技能相關的新證據，我們將重新評估。', en: 'Upload new evidence for this skill and we’ll re-assess.' },
  'doc.uploadEvidence': { zh: '上传证据', 'zh-TW': '上傳證據', en: 'Upload evidence' },
  'doc.uploadFirstHint': { zh: '请先上传至少一份文档。', 'zh-TW': '請先上傳至少一份文件。', en: 'Please upload at least one document first.' },
  'doc.output': { zh: '产出物：', 'zh-TW': '產出物：', en: 'Output: ' },
  'doc.chunksPrefix': { zh: '文档内容片段 (', 'zh-TW': '文件內容片段 (', en: 'Document Content Chunks (' },
  'doc.loadFailed': { zh: '加载失败', 'zh-TW': '載入失敗', en: 'Load Failed' },
  'doc.noChunks': { zh: '此文档尚未生成内容片段', 'zh-TW': '此文件尚未生成內容片段', en: 'No content chunks generated for this document' },
  'doc.dashboard': { zh: '仪表盘', 'zh-TW': '儀表板', en: 'Dashboard' },
  'doc.document': { zh: '文档', 'zh-TW': '文件', en: 'Document' },
  'doc.target': { zh: '目标', 'zh-TW': '目標', en: 'Target ' },
  'doc.details': { zh: '文档详情', 'zh-TW': '文件詳情', en: 'Document Details' },
};

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>('zh');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const savedLang = localStorage.getItem('skillsight-language') as Language;
    if (savedLang && ['zh', 'zh-TW', 'en'].includes(savedLang)) {
      setLanguageState(savedLang);
    }
  }, []);

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem('skillsight-language', lang);
  }, []);

  useEffect(() => {
    const langAttr = language === 'zh' ? 'zh-CN' : language === 'zh-TW' ? 'zh-TW' : 'en';
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('lang', langAttr);
    }
  }, [language]);

  const t = useCallback((key: string): string => {
    const translation = translations[key];
    if (!translation) {
      if (process.env.NODE_ENV !== 'production') {
        console.warn(`Translation missing for key: ${key}`);
      }
      return key;
    }
    return translation[language] ?? translation['zh'];
  }, [language]);

  // Always provide context so useLanguage() never throws (SSR-safe when !mounted)
  const value = mounted
    ? { language, setLanguage, t }
    : {
        language: 'zh' as Language,
        setLanguage: (() => {}) as (lang: Language) => void,
        t: ((key: string) => translations[key]?.zh ?? key) as (key: string) => string,
      };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

const defaultLanguageContext: LanguageContextType = {
  language: 'zh',
  setLanguage: () => {},
  t: (key: string) => key, // SSR fallback; translations may not be ready
};

export function useLanguage() {
  const context = useContext(LanguageContext);
  return context ?? defaultLanguageContext;
}

// ==========================================
// 3. 引导教程上下文
// ==========================================
interface TutorialContextType {
  showTutorial: boolean;
  currentStep: number;
  totalSteps: number;
  tutorialName: string;
  setTutorialName: (name: string) => void;
  startTutorial: () => void;
  nextStep: () => void;
  prevStep: () => void;
  skipTutorial: () => void;
  completeTutorial: () => void;
}

const TutorialContext = createContext<TutorialContextType | undefined>(undefined);

export function TutorialProvider({ children }: { children: ReactNode }) {
  const [showTutorial, setShowTutorial] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [tutorialName, setTutorialNameState] = useState('');
  const totalSteps = 5;
  const pathname = usePathname();

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const hasSeenTutorial = localStorage.getItem('skillsight-tutorial-completed');
    const user = localStorage.getItem('user');
    const savedName = localStorage.getItem('skillsight-onboarding-name');
    if (savedName) setTutorialNameState(savedName);
    const isDashboardOrHome = pathname === '/dashboard' || pathname === '/';
    if (!hasSeenTutorial && user && isDashboardOrHome) {
      timer = setTimeout(() => setShowTutorial(true), 800);
    }
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [pathname]);

  const setTutorialName = useCallback((name: string) => {
    const clean = name.trim();
    setTutorialNameState(clean);
    if (typeof localStorage !== 'undefined') {
      if (clean) localStorage.setItem('skillsight-onboarding-name', clean);
      else localStorage.removeItem('skillsight-onboarding-name');
    }
  }, []);

  const startTutorial = useCallback(() => {
    setCurrentStep(0);
    setShowTutorial(true);
  }, []);

  const nextStep = useCallback(() => {
    if (currentStep < totalSteps - 1) {
      setCurrentStep(prev => prev + 1);
    }
  }, [currentStep, totalSteps]);

  const prevStep = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1);
    }
  }, [currentStep]);

  const skipTutorial = useCallback(() => {
    setShowTutorial(false);
    if (typeof localStorage !== 'undefined') localStorage.setItem('skillsight-tutorial-completed', 'true');
  }, []);

  const completeTutorial = useCallback(() => {
    setShowTutorial(false);
    if (typeof localStorage !== 'undefined') localStorage.setItem('skillsight-tutorial-completed', 'true');
  }, []);

  return (
    <TutorialContext.Provider
      value={{
        showTutorial,
        currentStep,
        totalSteps,
        tutorialName,
        setTutorialName,
        startTutorial,
        nextStep,
        prevStep,
        skipTutorial,
        completeTutorial,
      }}
    >
      {children}
    </TutorialContext.Provider>
  );
}

const defaultTutorialContext: TutorialContextType = {
  showTutorial: false,
  currentStep: 0,
  totalSteps: 5,
  tutorialName: '',
  setTutorialName: () => {},
  startTutorial: () => {},
  nextStep: () => {},
  prevStep: () => {},
  skipTutorial: () => {},
  completeTutorial: () => {},
};

export function useTutorial() {
  const context = useContext(TutorialContext);
  return context ?? defaultTutorialContext;
}

export { getDateLocale } from './getDateLocale';
