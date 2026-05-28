/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { AnnotationFeature, BackendJobSummary, Project, Collaborator, PromptTemplateOption } from './types';
import { createLayoutDraftProject, formatCount, isCompleteBackendJob, mapJobToProject, normalizePromptTemplates } from './lib/jobs';
import Dashboard from './components/Dashboard';
import DatasetsPage from './components/DatasetsPage';
import Workspace from './components/Workspace';
import SecondAnnotationWorkspace from './components/SecondAnnotationWorkspace';
import PromptManagementPage from './components/PromptManagementPage';
import SettingsPage from './components/SettingsPage';
import GlowBackground from './components/GlowBackground';
import { motion, AnimatePresence } from 'motion/react';

export default function App() {
  // Screen views: 'dashboard' or 'workspace'
  const [activeScreen, setActiveScreen] = useState<'dashboard' | 'workspace' | 'secondAnnotation'>('dashboard');
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
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
  const [activeHeaderTab, setActiveHeaderTab] = useState<'projects' | 'datasets' | 'prompts' | 'analytics' | 'team' | 'settings'>('projects');
  const isDatasetsPage = activeScreen === 'dashboard' && activeHeaderTab === 'datasets';
  const isWorkspace = activeScreen === 'workspace' || activeScreen === 'secondAnnotation';

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
      const backendJobs = await fetchDatasetSummaries();
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

  const fetchDatasetSummaries = async (): Promise<BackendJobSummary[]> => {
    try {
      const response = await fetch('/api/datasets', { cache: 'no-store' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
      return payload.datasets || payload.jobs || [];
    } catch (datasetError) {
      console.warn('Falling back to legacy /api/jobs dataset list:', datasetError);
      const response = await fetch('/api/jobs', { cache: 'no-store' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
      return (payload.jobs || []).map((job: BackendJobSummary) => ({
        ...job,
        dataset_id: job.dataset_id || job.job_id,
        annotation_status: isCompleteBackendJob(job.status) ? 'first_annotated' : 'none',
        convert_status: 'none',
        converted_formats: [],
      }));
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
    setPromptTemplates((current) => {
      const exists = current.some((item) => item.id === savedTemplate.id);
      return exists
        ? current.map((item) => item.id === savedTemplate.id ? savedTemplate : item)
        : [...current, savedTemplate];
    });
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

  const handleOpenDataset = (jobId: string) => {
    const project = projects.find((item) => item.backendJobId === jobId);
    const job = jobs.find((item) => item.job_id === jobId);
    const targetProject = project || (job ? mapJobToProject(job) : null);
    if (!targetProject) {
      alert('未找到该数据集的后端分析结果，请刷新数据集列表后再试。');
      return;
    }
    setSelectedProject(targetProject);
    setActiveScreen('workspace');
  };

  const handleOpenSecondAnnotation = (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    setActiveScreen('secondAnnotation');
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
    <div className={`${isDatasetsPage || isWorkspace ? 'bg-surface-container-low p-0 text-on-surface' : 'bg-surface-container-low p-6 md:p-12 text-on-surface'} min-h-screen relative overflow-hidden flex items-center justify-center font-sans select-none`}>
      
      {/* Glow Effects backdrop elements */}
      {!isDatasetsPage && <GlowBackground />}

      {/* Main Container workspace wrapping matching the specified canvas aspect ratios */}
      <main className={`${isDatasetsPage || isWorkspace ? 'w-full min-h-screen bg-surface-container-low' : 'w-full max-w-[1600px] h-full max-h-[900px] min-h-[820px] bg-surface-container-lowest rounded-2xl shadow-[0_40px_100px_rgba(0,0,0,0.08)] border border-outline-variant/30'} flex flex-col overflow-hidden relative z-10`}>
        
        {/* Top Header Navigation bar (Standard across app state layout switching) */}
        {activeScreen === 'dashboard' && !isDatasetsPage && (
          <header className="flex justify-between items-center w-full px-10 bg-surface/80 backdrop-blur-xl border-outline-variant/30 border-b py-5 sticky top-0 z-50">
            <div className="flex items-center gap-12">
              <span className="text-3xl font-black tracking-tight text-primary cursor-pointer" onClick={() => setActiveScreen('dashboard')}>
                MarkHub
              </span>
              <nav className="hidden md:flex gap-8 items-center text-sm font-medium select-none">
                <button 
                  onClick={() => setActiveHeaderTab('projects')}
                  className={`pb-1 transition-all ${
                    activeHeaderTab === 'projects' 
                      ? 'text-primary border-b-2 border-primary font-bold'
                      : 'text-secondary hover:text-primary'
                  }`}
                >
                  项目
                </button>
                <button 
                  onClick={() => setActiveHeaderTab('datasets')}
                  className={`pb-1 transition-all ${
                    activeHeaderTab === 'datasets' 
                      ? 'text-primary border-b-2 border-primary font-bold'
                      : 'text-secondary hover:text-primary'
                  }`}
                >
                  数据集
                </button>
                <button 
                  onClick={() => setActiveHeaderTab('prompts')}
                  className={`pb-1 transition-all ${
                    activeHeaderTab === 'prompts' 
                      ? 'text-primary border-b-2 border-primary font-bold'
                      : 'text-secondary hover:text-primary'
                  }`}
                >
                  提示词管理
                </button>
                <button 
                  onClick={() => {
                    setActiveHeaderTab('analytics');
                    alert('Analytics Module: Visual model labeling regression indexes dashboard coming soon.');
                  }}
                  className={`pb-1 transition-all ${
                    activeHeaderTab === 'analytics' 
                      ? 'text-primary border-b-2 border-primary font-bold'
                      : 'text-secondary hover:text-primary'
                  }`}
                >
                  分析
                </button>
                <button 
                  onClick={() => setActiveHeaderTab('team')}
                  className={`pb-1 transition-all ${
                    activeHeaderTab === 'team' 
                      ? 'text-primary border-b-2 border-primary font-bold'
                      : 'text-secondary hover:text-primary'
                  }`}
                >
                  团队
                </button>
                <button 
                  onClick={() => setActiveHeaderTab('settings')}
                  className={`pb-1 transition-all ${
                    activeHeaderTab === 'settings' 
                      ? 'text-primary border-b-2 border-primary font-bold'
                      : 'text-secondary hover:text-primary'
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
                className="text-secondary hover:text-primary p-2 transition-all active:scale-95"
              >
                <Search className="w-5 h-5 focus:outline-none" />
              </button>
              
              <div 
                className="w-10 h-10 rounded-full overflow-hidden border border-outline-variant hover:border-outline cursor-pointer active:scale-95 duration-100"
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
                key={activeHeaderTab === 'datasets' ? 'datasets-view' : activeHeaderTab === 'prompts' ? 'prompts-view' : activeHeaderTab === 'settings' ? 'settings-view' : 'dashboard-view'}
                initial={{ opacity: 0, scale: 0.99 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.99 }}
                transition={{ duration: 0.25, ease: 'easeOut' }}
                className="flex flex-1 overflow-hidden w-full h-full"
              >
                {activeHeaderTab === 'datasets' ? (
                  <DatasetsPage
                    jobs={jobs}
                    onNavigate={setActiveHeaderTab}
                    onCreateDataset={handleOpenAnnotationFeature}
                    onOpenDataset={handleOpenDataset}
                    onSecondAnnotate={handleOpenSecondAnnotation}
                    onRefreshDatasets={loadRealDatasets}
                  />
                ) : activeHeaderTab === 'prompts' ? (
                  <PromptManagementPage />
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
            ) : activeScreen === 'workspace' ? (
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
            ) : (
              selectedDatasetId && (
                <motion.div
                  key="second-annotation-view"
                  initial={{ opacity: 0, filter: 'blur(3px)' }}
                  animate={{ opacity: 1, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, filter: 'blur(3px)' }}
                  transition={{ duration: 0.2 }}
                  className="flex flex-1 overflow-hidden w-full h-full"
                >
                  <SecondAnnotationWorkspace
                    datasetId={selectedDatasetId}
                    onGoBack={() => {
                      setActiveScreen('dashboard');
                      setSelectedDatasetId(null);
                      loadRealDatasets();
                    }}
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
