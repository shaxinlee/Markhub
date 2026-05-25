/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { Search, Languages, Type, Check, Globe2, FileText, Grid3X3, Square, Spline, Crosshair, FileEdit, Save } from 'lucide-react';
import { AnnotationFeature, BackendJobSummary, Project, Collaborator, PromptTemplateOption } from './types';
import Dashboard from './components/Dashboard';
import DatasetsPage from './components/DatasetsPage';
import Workspace from './components/Workspace';
import GlowBackground from './components/GlowBackground';
import { motion, AnimatePresence } from 'motion/react';

export default function App() {
  // Screen views: 'dashboard' or 'workspace'
  const [activeScreen, setActiveScreen] = useState<'dashboard' | 'workspace'>('dashboard');
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [language, setLanguage] = useState<'zh-CN'>('zh-CN');

  const [jobs, setJobs] = useState<BackendJobSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplateOption[]>([]);

  // Teammates database
  const [collaborators, setCollaborators] = useState<Collaborator[]>([
    {
      id: 'col_1',
      name: 'Alexander Rostov',
      role: 'Lead ML Researcher',
      avatar: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100&q=80',
      active: true
    },
    {
      id: 'col_2',
      name: 'Sarah Jenkins',
      role: 'Senior Project Annotator',
      avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&q=80',
      active: true
    },
    {
      id: 'col_3',
      name: 'Kenji Takahashi',
      role: 'CV Architecture Engineer',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&q=80',
      active: true
    },
    {
      id: 'col_4',
      name: 'Emily Watson',
      role: 'Data Pipelines Quality Controller',
      avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100&q=80',
      active: true
    }
  ]);

  // Dynamic system overview stats
  const [stats, setStats] = useState({
    totalImages: 0,
    totalAnnotations: '0',
    activeCollaborators: 0
  });

  // active Navbar header selection
  const [activeHeaderTab, setActiveHeaderTab] = useState<'projects' | 'datasets' | 'analytics' | 'team' | 'settings'>('projects');
  const isDatasetsPage = activeScreen === 'dashboard' && activeHeaderTab === 'datasets';

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = 'Markhub 标注工作台';
  }, [language]);

  useEffect(() => {
    loadRealDatasets();
    loadPromptTemplates();
  }, []);

  const loadRealDatasets = async () => {
    try {
      const response = await fetch('/api/jobs', { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
      const backendJobs: BackendJobSummary[] = payload.jobs || [];
      const realProjects = backendJobs.map(mapJobToProject);
      setJobs(backendJobs);
      setProjects(realProjects);
      setStats({
        totalImages: backendJobs.reduce((sum, job) => sum + (job.page_count || 0), 0),
        totalAnnotations: formatCount(backendJobs.reduce((sum, job) => sum + (job.block_count || 0), 0)),
        activeCollaborators: backendJobs.length,
      });
    } catch (error) {
      console.error('Failed to load backend datasets:', error);
      setJobs([]);
      setProjects([]);
      setStats({ totalImages: 0, totalAnnotations: '0', activeCollaborators: 0 });
    }
  };

  const loadPromptTemplates = async () => {
    try {
      const response = await fetch('/api/config', { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
      setPromptTemplates(normalizePromptTemplates(payload.prompt_templates || []));
    } catch (error) {
      console.error('Failed to load prompt templates:', error);
      setPromptTemplates([
        { id: 'default_template_1', name: '默认模板 1', category: 'layout', prompt: '' }
      ]);
    }
  };

  const handleSavePromptTemplate = async (template: PromptTemplateOption) => {
    const response = await fetch(`/api/prompt-templates/${template.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(template),
    });
    const payload = await response.json();
    if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
    const savedTemplate: PromptTemplateOption = normalizePromptTemplates([payload.prompt_template])[0];
    setPromptTemplates((current) => current.map((item) => item.id === savedTemplate.id ? savedTemplate : item));
    return savedTemplate;
  };

  // Triggered when adding a project from dashboard
  const handleCreateProject = (newProj: Omit<Project, 'id' | 'images'>) => {
    const freshProj: Project = {
      ...newProj,
      id: `proj_custom_${Date.now()}`,
      images: [
        'https://lh3.googleusercontent.com/aida-public/AB6AXuA8Vg0FsccBPKY0Dqx1Qe7KlonM5GY3dxlAnmDJvmMl0XFhDW8jPgVY8gJEQqh2ca4NTw1tTMzgo8FNVlibPV0_P9ekG5UqCsGmyYCHBRgKN_JSndOr_BuOq2v8f3UK9TDMJTNnAjjAlvX2g2vQ9aHu07ce9mebXb-GWLu-OxKCJkacxAG-TiRIOv3Zy0lR3eI9T5fVoS7hhKfCE9v5pkuUJzDQtO4c8zyal1XqPLg7XvI0l-EZ7T-jxghtTDSQMUPEdmh0HLDnNDg'
      ]
    };

    setSelectedProject(freshProj);
    setActiveScreen('workspace');
  };

  // Select project to enter workspace view
  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    setActiveScreen('workspace');
  };

  const handleOpenAnnotationFeature = (feature: AnnotationFeature) => {
    if (feature !== 'layout') {
      alert('该标注功能未上线');
      return;
    }
    const targetProject = projects[0] || createLayoutDraftProject();
    setSelectedProject(targetProject);
    setActiveScreen('workspace');
  };

  // Workspace completion updates
  const handleUpdateProjectProgress = (id: string, progress: number) => {
    setProjects(projects.map(p => p.id === id ? { ...p, progress } : p));
  };

  // Keep overview numbers grounded in backend analysis history.
  const handleIncreaseAnnotations = () => {
    loadRealDatasets();
  };

  return (
    <div className={`${isDatasetsPage ? 'bg-surface-container-low p-0 text-on-surface' : 'bg-[#0c0c0c] p-6 md:p-12 text-[#e5e5e5]'} min-h-screen relative overflow-hidden flex items-center justify-center font-sans select-none`}>
      
      {/* Glow Effects backdrop elements */}
      {!isDatasetsPage && <GlowBackground />}

      {/* Main Container workspace wrapping matching the specified canvas aspect ratios */}
      <main className={`${isDatasetsPage ? 'w-full min-h-screen bg-surface-container-low' : 'w-full max-w-[1600px] h-full max-h-[900px] min-h-[820px] bg-[#0c0c0c] rounded-2xl shadow-[0_40px_100px_rgba(0,0,0,0.8)] border border-white/10'} flex flex-col overflow-hidden relative z-10`}>
        
        {/* Top Header Navigation bar (Standard across app state layout switching) */}
        {activeScreen === 'dashboard' && !isDatasetsPage && (
          <header className="flex justify-between items-center w-full px-10 bg-[#0c0c0c]/80 backdrop-blur-xl border-white/10 border-b py-5 sticky top-0 z-50">
            <div className="flex items-center gap-12">
              <span className="font-serif italic text-3xl tracking-tighter text-white cursor-pointer" onClick={() => setActiveScreen('dashboard')}>
                MarkHub.
              </span>
              <nav className="hidden md:flex gap-10 items-center text-[10px] uppercase tracking-[0.25em] font-medium opacity-80 select-none">
                <button 
                  onClick={() => setActiveHeaderTab('projects')}
                  className={`pb-1 transition-all hover:opacity-100 ${
                    activeHeaderTab === 'projects' 
                      ? 'text-white border-b border-white font-bold opacity-100' 
                      : 'text-[#e5e5e5] opacity-50'
                  }`}
                >
                  项目
                </button>
                <button 
                  onClick={() => setActiveHeaderTab('datasets')}
                  className={`pb-1 transition-all hover:opacity-100 ${
                    activeHeaderTab === 'datasets' 
                      ? 'text-white border-b border-white font-bold opacity-100' 
                      : 'text-[#e5e5e5] opacity-50'
                  }`}
                >
                  数据集
                </button>
                <button 
                  onClick={() => {
                    setActiveHeaderTab('analytics');
                    alert('Analytics Module: Visual model labeling regression indexes dashboard coming soon.');
                  }}
                  className={`pb-1 transition-all hover:opacity-100 ${
                    activeHeaderTab === 'analytics' 
                      ? 'text-white border-b border-white font-bold opacity-100' 
                      : 'text-[#e5e5e5] opacity-50'
                  }`}
                >
                  分析
                </button>
                <button 
                  onClick={() => setActiveHeaderTab('team')}
                  className={`pb-1 transition-all hover:opacity-100 ${
                    activeHeaderTab === 'team' 
                      ? 'text-white border-b border-white font-bold opacity-100' 
                      : 'text-[#e5e5e5] opacity-50'
                  }`}
                >
                  团队
                </button>
                <button 
                  onClick={() => setActiveHeaderTab('settings')}
                  className={`pb-1 transition-all hover:opacity-100 ${
                    activeHeaderTab === 'settings' 
                      ? 'text-white border-b border-white font-bold opacity-100' 
                      : 'text-[#e5e5e5] opacity-50'
                  }`}
                >
                  设置
                </button>
              </nav>
            </div>

            {/* Topbar User actions Profile tools */}
            <div className="flex items-center gap-5">
              <button 
                onClick={() => alert('Global Search: Query tags directly on dashboard filters below.')}
                className="text-white/60 hover:text-white p-2 transition-all active:scale-95"
              >
                <Search className="w-5 h-5 focus:outline-none" />
              </button>
              
              <div 
                className="w-9 h-9 rounded-full overflow-hidden border border-white/20 hover:border-white/50 cursor-pointer active:scale-95 duration-100"
                onClick={() => alert(`MarkHub Administrator Profile - Registered Email: shaxinlee3@gmail.com`)}
                title="View Profile logs"
              >
                <img 
                  alt="User profile avatar headshot" 
                  referrerPolicy="no-referrer"
                  className="w-full h-full object-cover" 
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuADbeX1DZktwg6S1FYv2bvxtwWXDNYYVLjmi2OEN5FDfL9_GHYt2bcai2MZKlMDkA5E5Gs1HkhofWlsPQDEDRTBXCoFXHNC0eLAXVmsOHwzyB9INCax2srS9qvD6GDewdKqvPJai8iGUatIZtmercaRF2DJjEBCPqxO_DnPlE_k2cgs_lwg7uLcXwUkUMwfVfWj-7QX17RP_c0ClQET24HeaFblKUGjlN8nuCgLu_sFrOJsg7khJsiZdfamAdF03ij9pnzAXHwMWkU"
                />
              </div>
            </div>
          </header>
        )}

        {/* Dynamic Transition Canvas Content Layout switching */}
        <div className="flex-1 flex overflow-hidden relative w-full h-full">
          <AnimatePresence mode="wait">
            {activeScreen === 'dashboard' ? (
              <motion.div
                key={activeHeaderTab === 'datasets' ? 'datasets-view' : activeHeaderTab === 'settings' ? 'settings-view' : 'dashboard-view'}
                initial={{ opacity: 0, scale: 0.99 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.99 }}
                transition={{ duration: 0.25, ease: 'easeOut' }}
                className="flex flex-1 overflow-hidden w-full h-full"
              >
                {activeHeaderTab === 'datasets' ? (
                  <DatasetsPage jobs={jobs} onNavigate={setActiveHeaderTab} />
                ) : activeHeaderTab === 'settings' ? (
                  <SettingsPage
                    language={language}
                    promptTemplates={promptTemplates}
                    onLanguageChange={setLanguage}
                    onSavePromptTemplate={handleSavePromptTemplate}
                  />
                ) : (
                  <Dashboard 
                    projects={projects}
                    collaborators={collaborators}
                    onCreateProject={handleCreateProject}
                    onSelectProject={handleSelectProject}
                    onOpenAnnotationFeature={handleOpenAnnotationFeature}
                    stats={stats}
                  />
                )}
              </motion.div>
            ) : (
              selectedProject && (
                <motion.div
                  key="workspace-view"
                  initial={{ opacity: 0, filter: 'blur(3px)' }}
                  animate={{ opacity: 1, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, filter: 'blur(3px)' }}
                  transition={{ duration: 0.2 }}
                  className="flex flex-1 overflow-hidden w-full h-full"
                >
                  <Workspace 
                    project={selectedProject}
                    onGoBack={() => {
                      setActiveScreen('dashboard');
                      setSelectedProject(null);
                      loadRealDatasets();
                    }}
                    onUpdateProjectProgress={handleUpdateProjectProgress}
                    onIncreaseAnnotationsCount={handleIncreaseAnnotations}
                  />
                </motion.div>
              )
            )}
          </AnimatePresence>
        </div>

      </main>
    </div>
  );
}

interface SettingsPageProps {
  language: 'zh-CN';
  promptTemplates: PromptTemplateOption[];
  onLanguageChange: (language: 'zh-CN') => void;
  onSavePromptTemplate: (template: PromptTemplateOption) => Promise<PromptTemplateOption>;
}

function SettingsPage({ language, promptTemplates, onLanguageChange, onSavePromptTemplate }: SettingsPageProps) {
  return (
    <section className="flex flex-1 overflow-y-auto custom-scrollbar bg-[#0c0c0c] text-[#e5e5e5]">
      <aside className="w-20 bg-[#0e0e0e] border-r border-white/10 flex flex-col items-center py-10 space-y-12 h-full select-none z-10">
        <div className="p-3 text-white bg-white/10 border border-white/5 rounded-none transition-all">
          <Globe2 className="w-5 h-5" />
        </div>
      </aside>

      <div className="flex-1 px-12 py-12 space-y-10">
        <div className="border-b border-white/10 pb-8">
          <span className="text-[10px] uppercase tracking-[0.3em] text-white/40 font-mono">System Preferences</span>
          <h1 className="font-serif italic text-4xl leading-tight text-white tracking-tight mt-3">
            设置
          </h1>
          <p className="text-white/55 text-sm max-w-2xl mt-3 leading-relaxed">
            管理 Markhub 的界面语言和显示字体。当前版本默认使用中文界面，并采用适合商业产品的中文字体栈。
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-8">
          <div className="space-y-8">
            <div className="bg-[#141414] border border-white/10 rounded-none p-6">
              <div className="flex items-start justify-between gap-6 border-b border-white/10 pb-5 mb-5">
                <div>
                  <div className="flex items-center gap-2 text-white mb-2">
                    <Languages className="w-5 h-5" />
                    <h2 className="text-sm uppercase tracking-[0.2em] font-bold">语言</h2>
                  </div>
                  <p className="text-xs text-white/50 leading-relaxed">
                    选择网页显示语言。当前只开放中文，后续可以继续扩展英文或更多语言。
                  </p>
                </div>
                <span className="text-[9px] uppercase tracking-[0.2em] font-mono text-emerald-300 bg-emerald-400/10 border border-emerald-400/20 px-2 py-1">
                  默认中文
                </span>
              </div>

              <label htmlFor="languageSelect" className="block text-[10px] uppercase tracking-wider font-bold text-white/50 mb-2">
                界面语言
              </label>
              <select
                id="languageSelect"
                value={language}
                onChange={(event) => onLanguageChange(event.target.value as 'zh-CN')}
                className="w-full max-w-md bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium"
              >
                <option value="zh-CN">中文（简体）</option>
              </select>

              <div className="mt-5 flex items-center gap-2 text-[11px] text-white/45 font-mono">
                <Check className="w-4 h-4 text-emerald-300" />
                <span>当前网页语言已设置为 zh-CN</span>
              </div>
            </div>

            <div className="bg-[#141414] border border-white/10 rounded-none p-6">
              <div className="flex items-center gap-2 text-white mb-2">
                <Type className="w-5 h-5" />
                <h2 className="text-sm uppercase tracking-[0.2em] font-bold">中文字体</h2>
              </div>
              <p className="text-xs text-white/50 leading-relaxed max-w-2xl">
                默认字体使用 `Noto Sans SC`，并回退到 `PingFang SC`、`Microsoft YaHei`。`Noto Sans SC` 对应思源黑体体系，开源可商用，适合中文后台、数据标注平台和企业级应用界面。
              </p>

              <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border border-white/10 bg-white/[0.02] p-5">
                  <span className="text-[10px] uppercase tracking-[0.24em] text-white/40 font-mono">Preview</span>
                  <p className="mt-4 text-2xl font-bold text-white tracking-normal">
                    Markhub 智能文档标注平台
                  </p>
                  <p className="mt-2 text-sm text-white/55 leading-7">
                    中文界面默认启用，适合长文本、表格、标题层级和版面分析结果展示。
                  </p>
                </div>
                <div className="border border-white/10 bg-white/[0.02] p-5 font-mono">
                  <span className="text-[10px] uppercase tracking-[0.24em] text-white/40">Font Stack</span>
                  <p className="mt-4 text-xs leading-6 text-white/60 break-words">
                    Noto Sans SC, PingFang SC, Microsoft YaHei, Inter, system-ui, sans-serif
                  </p>
                </div>
              </div>
            </div>

            <PromptTemplateManager
              promptTemplates={promptTemplates}
              onSavePromptTemplate={onSavePromptTemplate}
            />
          </div>

          <aside className="bg-[#141414] border border-white/10 rounded-none p-6 h-fit">
            <span className="text-[10px] uppercase tracking-[0.3em] text-white/40 font-mono">Current</span>
            <div className="mt-5 space-y-4">
              <div className="flex justify-between items-center border-b border-white/10 pb-3">
                <span className="text-xs text-white/45">语言</span>
                <span className="text-xs text-white font-bold">中文（简体）</span>
              </div>
              <div className="flex justify-between items-center border-b border-white/10 pb-3">
                <span className="text-xs text-white/45">HTML Lang</span>
                <span className="text-xs text-white font-mono">zh-CN</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-white/45">主字体</span>
                <span className="text-xs text-white font-bold">Noto Sans SC</span>
              </div>
              <div className="flex justify-between items-center border-t border-white/10 pt-3">
                <span className="text-xs text-white/45">Layout 提示词</span>
                <span className="text-xs text-white font-bold">
                  {promptTemplates.filter((template) => template.category === 'layout').length}
                </span>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}

const PROMPT_CATEGORY_META: Array<{
  id: AnnotationFeature;
  label: string;
  description: string;
  icon: React.ReactNode;
  available: boolean;
}> = [
  { id: 'bounding_box', label: 'Bounding Box', description: '矩形框标注提示词', icon: <Square className="w-4 h-4" />, available: false },
  { id: 'polygon', label: 'Polygon Segment', description: '多边形分割提示词', icon: <Spline className="w-4 h-4" />, available: false },
  { id: 'layout', label: 'Layout Analysis', description: '文档版面分析提示词', icon: <Grid3X3 className="w-4 h-4" />, available: true },
  { id: 'keypoints', label: 'Keypoints Picker', description: '关键点标注提示词', icon: <Crosshair className="w-4 h-4" />, available: false },
  { id: 'text_transcription', label: 'Text Transcription', description: '文字转录提示词', icon: <FileEdit className="w-4 h-4" />, available: false },
];

interface PromptTemplateManagerProps {
  promptTemplates: PromptTemplateOption[];
  onSavePromptTemplate: (template: PromptTemplateOption) => Promise<PromptTemplateOption>;
}

function PromptTemplateManager({ promptTemplates, onSavePromptTemplate }: PromptTemplateManagerProps) {
  const [activeCategory, setActiveCategory] = useState<AnnotationFeature>('layout');
  const [selectedTemplateId, setSelectedTemplateId] = useState('default_template_1');
  const [draftPrompt, setDraftPrompt] = useState('');
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const categoryTemplates = promptTemplates.filter((template) => template.category === activeCategory);
  const selectedTemplate = categoryTemplates.find((template) => template.id === selectedTemplateId) || categoryTemplates[0];
  const activeMeta = PROMPT_CATEGORY_META.find((item) => item.id === activeCategory) || PROMPT_CATEGORY_META[2];

  useEffect(() => {
    if (categoryTemplates.length && !categoryTemplates.some((template) => template.id === selectedTemplateId)) {
      setSelectedTemplateId(categoryTemplates[0].id);
    }
  }, [activeCategory, categoryTemplates, selectedTemplateId]);

  useEffect(() => {
    setDraftPrompt(selectedTemplate?.prompt || '');
    setSaveState('idle');
    setErrorMessage('');
  }, [selectedTemplate?.id, selectedTemplate?.prompt]);

  const handleSave = async () => {
    if (!selectedTemplate || saveState === 'saving') return;
    setSaveState('saving');
    setErrorMessage('');
    try {
      await onSavePromptTemplate({ ...selectedTemplate, prompt: draftPrompt });
      setSaveState('saved');
    } catch (error) {
      setSaveState('error');
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div className="bg-[#141414] border border-white/10 rounded-none p-6">
      <div className="flex items-start justify-between gap-6 border-b border-white/10 pb-5 mb-5">
        <div>
          <div className="flex items-center gap-2 text-white mb-2">
            <FileText className="w-5 h-5" />
            <h2 className="text-sm uppercase tracking-[0.2em] font-bold">提示词模板</h2>
          </div>
          <p className="text-xs text-white/50 leading-relaxed max-w-2xl">
            按标注类型维护模型提示词。当前已上线 Layout Analysis，所以“默认模板 1”归类在 Layout 提示词中，并会用于后续文档版面分析。
          </p>
        </div>
        <span className="text-[9px] uppercase tracking-[0.2em] font-mono text-white/45 bg-white/[0.03] border border-white/10 px-2 py-1">
          {promptTemplates.length} Templates
        </span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[260px_minmax(0,1fr)] gap-5">
        <div className="space-y-2">
          {PROMPT_CATEGORY_META.map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => setActiveCategory(category.id)}
              className={`w-full border px-4 py-3 text-left transition-all active:scale-[0.99] ${
                activeCategory === category.id
                  ? 'border-white/25 bg-white/[0.08] text-white'
                  : 'border-white/10 bg-white/[0.02] text-white/55 hover:bg-white/[0.04] hover:text-white/80'
              }`}
            >
              <div className="flex items-center gap-3">
                <span className={category.available ? 'text-emerald-300' : 'text-white/35'}>{category.icon}</span>
                <span className="text-[10px] uppercase tracking-[0.18em] font-bold">{category.label}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-[11px] text-white/40">{category.description}</span>
                <span className={`text-[8px] uppercase tracking-[0.14em] font-mono ${category.available ? 'text-emerald-300' : 'text-white/25'}`}>
                  {category.available ? 'Live' : 'Soon'}
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="min-h-[420px] border border-white/10 bg-[#0e0e0e] p-5">
          {categoryTemplates.length && selectedTemplate ? (
            <div className="flex h-full flex-col">
              <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <span className="text-[10px] uppercase tracking-[0.25em] text-white/35 font-mono">{activeMeta.label}</span>
                  <h3 className="mt-2 font-serif italic text-xl text-white">{selectedTemplate.name}</h3>
                </div>
                <select
                  value={selectedTemplate.id}
                  onChange={(event) => setSelectedTemplateId(event.target.value)}
                  className="bg-[#141414] border border-white/10 rounded-none px-3 py-2 text-xs text-white focus:outline-none focus:border-white/30"
                >
                  {categoryTemplates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
              </div>

              <label htmlFor="promptTemplateEditor" className="mb-2 block text-[10px] uppercase tracking-wider font-bold text-white/45">
                Prompt Content
              </label>
              <textarea
                id="promptTemplateEditor"
                value={draftPrompt}
                onChange={(event) => {
                  setDraftPrompt(event.target.value);
                  setSaveState('idle');
                }}
                className="min-h-[280px] flex-1 resize-none bg-black/20 border border-white/10 rounded-none p-4 text-xs leading-6 text-white/80 outline-none focus:border-white/30 custom-scrollbar"
                spellCheck={false}
              />

              <div className="mt-4 flex flex-col gap-3 border-t border-white/10 pt-4 md:flex-row md:items-center md:justify-between">
                <p className={`text-[11px] ${saveState === 'error' ? 'text-red-300' : saveState === 'saved' ? 'text-emerald-300' : 'text-white/40'}`}>
                  {saveState === 'saving' ? '正在保存提示词模板...' : saveState === 'saved' ? '已保存，后续 Layout 分析会使用这份提示词。' : saveState === 'error' ? errorMessage : '修改后点击保存即可更新后端模板。'}
                </p>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saveState === 'saving'}
                  className="inline-flex items-center justify-center gap-2 bg-white px-5 py-2.5 text-[10px] font-bold uppercase tracking-[0.18em] text-black transition-all hover:bg-white/90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Save className="w-4 h-4" />
                  Save Prompt
                </button>
              </div>
            </div>
          ) : (
            <div className="flex h-full min-h-[360px] flex-col items-center justify-center text-center">
              <div className="mb-4 text-white/25">{activeMeta.icon}</div>
              <h3 className="font-serif italic text-xl text-white/80">功能未上线</h3>
              <p className="mt-2 max-w-sm text-xs leading-6 text-white/45">
                {activeMeta.label} 的提示词模板会在对应标注能力上线后开放编辑。
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function mapJobToProject(job: BackendJobSummary): Project {
  const progress = job.page_count > 0 ? Math.round(((job.completed_pages || 0) / job.page_count) * 100) : 0;
  const thumbnail = job.first_page_url || '';

  return {
    id: job.job_id,
    backendJobId: job.job_id,
    name: job.filename || `Dataset ${job.job_id}`,
    type: 'CV',
    progress,
    thumbnail,
    description: `${job.page_count || 0} pages · ${job.block_count || 0} layout blocks · ${job.model || 'Unknown model'}`,
    totalImages: job.page_count || 0,
    totalAnnotations: job.block_count || 0,
    category: 'PDF Layout Analysis',
    images: thumbnail ? [thumbnail] : [],
    model: job.model || 'Unknown model',
    status: job.status,
    updatedAt: job.updated_at,
    promptTemplateName: job.prompt_template?.name,
    errorCount: job.error_count || 0,
  };
}

function createLayoutDraftProject(): Project {
  return {
    id: `layout_draft_${Date.now()}`,
    name: 'Layout Analysis Workspace',
    type: 'CV',
    progress: 0,
    thumbnail: '',
    description: 'Upload a PDF document to start backend layout analysis.',
    totalImages: 0,
    totalAnnotations: 0,
    category: 'PDF Layout Analysis',
    images: [],
  };
}

function normalizePromptTemplates(items: unknown[]): PromptTemplateOption[] {
  return items
    .filter((item): item is Partial<PromptTemplateOption> => Boolean(item) && typeof item === 'object')
    .map((item) => ({
      id: String(item.id || 'default_template_1'),
      name: String(item.name || '默认模板 1'),
      category: (item.category || 'layout') as AnnotationFeature,
      prompt: typeof item.prompt === 'string' ? item.prompt : '',
    }));
}

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}
