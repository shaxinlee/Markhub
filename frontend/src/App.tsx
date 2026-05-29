/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { BarChart3, Users } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { AnnotationFeature, BackendJobSummary, Project, Collaborator } from './types';
import { createLayoutDraftProject, formatCount, isCompleteBackendJob, mapJobToProject } from './lib/jobs';
import AppShell, { AppTab } from './components/AppShell';
import Dashboard from './components/Dashboard';
import DatasetsPage from './components/DatasetsPage';
import Workspace from './components/Workspace';
import SecondAnnotationWorkspace from './components/SecondAnnotationWorkspace';
import PromptManagementPage from './components/PromptManagementPage';
import SettingsPage from './components/SettingsPage';

export default function App() {
  const [activeScreen, setActiveScreen] = useState<'dashboard' | 'workspace' | 'secondAnnotation'>('dashboard');
  const [activeHeaderTab, setActiveHeaderTab] = useState<AppTab>('projects');
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [language, setLanguage] = useState<'zh-CN'>('zh-CN');

  const [jobs, setJobs] = useState<BackendJobSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [collaborators] = useState<Collaborator[]>([
    { id: 'col_1', name: 'Alexander Rostov', role: 'Lead ML Researcher', avatar: '', active: true },
    { id: 'col_2', name: 'Sarah Jenkins', role: 'Senior Project Annotator', avatar: '', active: true },
    { id: 'col_3', name: 'Kenji Takahashi', role: 'CV Architecture Engineer', avatar: '', active: true },
    { id: 'col_4', name: 'Emily Watson', role: 'Data Pipelines Quality Controller', avatar: '', active: true },
  ]);

  const [stats, setStats] = useState({
    totalImages: 0,
    totalAnnotations: '0',
    activeCollaborators: 0,
  });

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = 'Markhub 标注工作台';
  }, [language]);

  useEffect(() => {
    loadRealDatasets();
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

  const handleNavigate = (tab: AppTab) => {
    setActiveHeaderTab(tab);
    setActiveScreen('dashboard');
    setSelectedProject(null);
    setSelectedDatasetId(null);
  };

  const handleCreateProject = (newProj: Omit<Project, 'id' | 'images'>) => {
    const freshProj: Project = {
      ...newProj,
      id: `proj_custom_${Date.now()}`,
      images: [],
    };
    setSelectedProject(freshProj);
    setActiveScreen('workspace');
  };

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

  const handleUpdateProjectProgress = (id: string, progress: number) => {
    setProjects((current) => current.map((project) => project.id === id ? { ...project, progress } : project));
  };

  const handleIncreaseAnnotations = () => {
    loadRealDatasets();
  };

  return (
    <AnimatePresence mode="wait">
      {activeScreen === 'dashboard' ? (
        <AppShell activeTab={activeHeaderTab} onNavigate={handleNavigate}>
          <motion.div
            key={`${activeHeaderTab}-view`}
            initial={{ opacity: 0, scale: 0.99 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.99 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="flex min-h-[calc(100vh-4rem)] w-full overflow-hidden"
          >
            {activeHeaderTab === 'datasets' ? (
              <DatasetsPage
                jobs={jobs}
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
                onLanguageChange={setLanguage}
              />
            ) : activeHeaderTab === 'analytics' ? (
              <PlaceholderPage
                icon={<BarChart3 className="h-8 w-8" />}
                title="分析"
                description="模型质量、数据处理吞吐和转换结果统计会统一放在这里。"
              />
            ) : activeHeaderTab === 'team' ? (
              <PlaceholderPage
                icon={<Users className="h-8 w-8" />}
                title="团队"
                description="当前团队成员、标注协作和权限视图会统一放在这里。"
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
        </AppShell>
      ) : activeScreen === 'workspace' && selectedProject ? (
        <motion.div
          key="workspace-view"
          initial={{ opacity: 0, filter: 'blur(3px)' }}
          animate={{ opacity: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, filter: 'blur(3px)' }}
          transition={{ duration: 0.2 }}
          className="flex h-screen w-full overflow-hidden bg-surface-container-low text-on-surface"
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
      ) : activeScreen === 'secondAnnotation' && selectedDatasetId ? (
        <motion.div
          key="second-annotation-view"
          initial={{ opacity: 0, filter: 'blur(3px)' }}
          animate={{ opacity: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, filter: 'blur(3px)' }}
          transition={{ duration: 0.2 }}
          className="flex h-screen w-full overflow-hidden bg-surface-container-low text-on-surface"
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
      ) : null}
    </AnimatePresence>
  );
}

function PlaceholderPage({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <section className="w-full overflow-y-auto p-gutter md:p-[40px]">
      <div className="mx-auto max-w-7xl rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-10">
        <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-[0.75rem] bg-surface-container-high text-primary">
          {icon}
        </div>
        <span className="text-label-sm font-bold uppercase tracking-[0.24em] text-on-surface-variant">MarkHub</span>
        <h1 className="mt-3 text-headline-lg font-semibold text-primary">{title}</h1>
        <p className="mt-3 max-w-2xl text-body-md text-on-surface-variant">{description}</p>
      </div>
    </section>
  );
}
