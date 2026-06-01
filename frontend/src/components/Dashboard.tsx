/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useMemo, useState } from 'react';
import {
  ArrowUpRight,
  CheckCircle,
  Crosshair,
  Database,
  FileEdit,
  FileText,
  Grid3X3,
  Plus,
  Search,
  Spline,
  Square,
  Users,
  X,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { AnnotationFeature, Project, Collaborator } from '../types';

interface DashboardProps {
  projects: Project[];
  collaborators: Collaborator[];
  onCreateProject: (project: Omit<Project, 'id' | 'images'>) => void;
  onSelectProject: (project: Project) => void;
  onOpenAnnotationFeature: (feature: AnnotationFeature) => void;
  stats: {
    totalImages: number;
    totalAnnotations: string;
    activeCollaborators: number;
  };
}

const ANNOTATION_FEATURES: Array<{
  id: AnnotationFeature;
  label: string;
  description: string;
  status: 'online' | 'coming_soon';
  icon: React.ReactNode;
}> = [
  { id: 'layout', label: '版面分析标注', description: 'PDF 页面渲染、版面块识别、人工修正。', status: 'online', icon: <Grid3X3 className="h-4 w-4" /> },
  { id: 'bounding_box', label: '目标框标注', description: '通用矩形框标注能力，支持拖拽画框、标签管理、批量上传。', status: 'online', icon: <Square className="h-4 w-4" /> },
  { id: 'polygon', label: '多边形分割', description: '复杂区域轮廓标注。', status: 'coming_soon', icon: <Spline className="h-4 w-4" /> },
  { id: 'keypoints', label: '关键点标注', description: '结构点位和姿态类任务。', status: 'coming_soon', icon: <Crosshair className="h-4 w-4" /> },
  { id: 'text_transcription', label: '文本转录', description: '图片文字转写和校验。', status: 'coming_soon', icon: <FileEdit className="h-4 w-4" /> },
];

export default function Dashboard({
  projects,
  collaborators,
  onCreateProject,
  onSelectProject,
  onOpenAnnotationFeature,
  stats,
}: DashboardProps) {
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [isCollaboratorsOpen, setIsCollaboratorsOpen] = useState(false);
  const [isEnterpriseModalOpen, setIsEnterpriseModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState('');
  const [newProjDesc, setNewProjDesc] = useState('');
  const [newProjType, setNewProjType] = useState<'CV' | 'Multimodal' | 'Keypoints' | 'NLP'>('CV');
  const [newProjCategory, setNewProjCategory] = useState('Layout Analysis');
  const [searchTerm, setSearchTerm] = useState('');

  const filteredProjects = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) return projects;
    return projects.filter((project) => {
      return `${project.name} ${project.category} ${project.description}`.toLowerCase().includes(keyword);
    });
  }, [projects, searchTerm]);

  const handleCreateSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!newProjName.trim()) return;
    onCreateProject({
      name: newProjName.trim(),
      description: newProjDesc.trim() || '自定义文档版面分析标注项目。',
      type: newProjType,
      progress: 0,
      thumbnail: '',
      totalImages: 1,
      totalAnnotations: 0,
      category: newProjCategory,
    });
    setNewProjName('');
    setNewProjDesc('');
    setNewProjType('CV');
    setNewProjCategory('Layout Analysis');
    setIsNewProjectModalOpen(false);
  };

  return (
    <section id="markhub-dashboard" className="w-full overflow-y-auto bg-surface-container-low p-gutter text-on-surface md:p-[40px]">
      <div className="mx-auto grid max-w-7xl gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-[40px]">
          <section className="rounded-[1.5rem] border border-surface-variant bg-surface-container-lowest p-[32px] shadow-[0_20px_50px_rgba(0,0,0,0.02)] md:p-[40px]">
            <div className="mb-10 flex flex-col justify-between gap-6 md:flex-row md:items-end">
              <div>
                <span className="text-label-sm font-bold uppercase tracking-[0.24em] text-on-surface-variant">Project Workspace</span>
                <h1 className="mt-3 text-headline-lg font-semibold text-primary">项目</h1>
                <p className="mt-2 max-w-2xl text-body-md text-on-surface-variant">
                  统一查看后端已处理数据集、进入标注工作台，并创建新的版面分析任务。
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => setIsCollaboratorsOpen(true)}
                  className="flex items-center gap-2 rounded-[0.75rem] border border-outline-variant/50 bg-surface-container-lowest px-4 py-3 text-label-md font-semibold text-primary transition-colors hover:bg-surface-container"
                >
                  <Users className="h-4 w-4" />
                  团队
                </button>
                <button
                  type="button"
                  onClick={() => setIsNewProjectModalOpen(true)}
                  className="flex items-center gap-2 rounded-[0.75rem] bg-primary px-5 py-3 text-label-md font-semibold text-on-primary transition-colors hover:bg-primary/90"
                >
                  <Plus className="h-4 w-4" />
                  新建项目
                </button>
              </div>
            </div>

            <div className="mb-10 grid grid-cols-1 gap-6 md:grid-cols-3">
              <MetricCard label="总页数" value={stats.totalImages.toLocaleString()} note="Backend synced" />
              <MetricCard label="版面块" value={stats.totalAnnotations} note="Layout blocks" />
              <MetricCard label="数据集" value={stats.activeCollaborators.toLocaleString()} note="Synced list" />
            </div>

            <div className="mb-8 flex flex-col justify-between gap-4 border-b border-surface-variant pb-4 md:flex-row md:items-center">
              <div className="relative w-full md:max-w-md">
                <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-on-surface-variant" />
                <input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  className="h-12 w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container py-3 pl-10 pr-4 text-body-md outline-none transition-colors placeholder:text-on-surface-variant focus:border-primary"
                  placeholder="搜索项目或数据集"
                  type="search"
                />
              </div>
              <span className="text-label-md font-semibold text-on-surface-variant">
                {filteredProjects.length} 个项目
              </span>
            </div>

            {filteredProjects.length === 0 ? (
              <EmptyState
                title={projects.length === 0 ? '还没有后端数据集' : '没有匹配的项目'}
                description={projects.length === 0 ? '进入版面分析标注工作台，上传 PDF 并启动分析后会自动生成项目记录。' : '调整搜索关键词后再试。'}
                actionLabel={projects.length === 0 ? '开始版面分析' : '清空搜索'}
                onAction={() => projects.length === 0 ? onOpenAnnotationFeature('layout') : setSearchTerm('')}
              />
            ) : (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {filteredProjects.map((project) => (
                  <React.Fragment key={project.id}>
                    <ProjectCard project={project} onSelect={() => onSelectProject(project)} />
                  </React.Fragment>
                ))}
              </div>
            )}
          </section>
        </div>

        <aside className="space-y-6">
          <section className="rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-6">
            <h2 className="text-label-md font-bold uppercase tracking-[0.2em] text-on-surface-variant">标注能力</h2>
            <div className="mt-5 space-y-3">
              {ANNOTATION_FEATURES.map((feature) => {
                const online = feature.status === 'online';
                return (
                  <button
                    key={feature.id}
                    type="button"
                    onClick={() => onOpenAnnotationFeature(feature.id)}
                    className="flex w-full items-center gap-3 rounded-[0.75rem] border border-outline-variant/40 bg-surface-container-lowest p-3 text-left transition-colors hover:bg-surface-container"
                  >
                    <span className="flex h-9 w-9 items-center justify-center rounded-[0.75rem] bg-surface-container-high text-primary">
                      {feature.icon}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-label-md font-semibold text-primary">{feature.label}</span>
                      <span className="mt-0.5 block truncate text-label-sm text-on-surface-variant">{feature.description}</span>
                    </span>
                    <span className={`rounded-full px-2 py-1 text-label-sm font-semibold ${online ? 'bg-primary text-on-primary' : 'bg-surface-container-high text-on-surface-variant'}`}>
                      {online ? '可用' : '待开发'}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-[0.75rem] bg-surface-container-high text-primary">
                <Database className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-label-md font-bold text-primary">企业工作区</h2>
                <p className="text-label-sm text-on-surface-variant">Data Science Lab</p>
              </div>
            </div>
            <p className="mt-4 text-label-md leading-6 text-on-surface-variant">
              统一管理数据集处理、提示词、人工校验和格式转换，减少页面之间的操作跳转。
            </p>
            <button
              type="button"
              onClick={() => setIsEnterpriseModalOpen(true)}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-[0.75rem] border border-outline-variant/50 px-4 py-3 text-label-md font-semibold text-primary hover:bg-surface-container"
            >
              <ArrowUpRight className="h-4 w-4" />
              查看说明
            </button>
          </section>
        </aside>
      </div>

      <AnimatePresence>
        {isNewProjectModalOpen && (
          <Modal title="新建标注项目" onClose={() => setIsNewProjectModalOpen(false)}>
            <form onSubmit={handleCreateSubmit} className="space-y-5">
              <Field label="项目名称" value={newProjName} onChange={setNewProjName} required placeholder="例如：合同版面解析" />
              <Textarea label="项目描述" value={newProjDesc} onChange={setNewProjDesc} placeholder="描述数据集来源和标注目标" />
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <SelectField
                  label="模型类型"
                  value={newProjType}
                  onChange={(value) => setNewProjType(value as typeof newProjType)}
                  options={[
                    ['CV', 'Computer Vision'],
                    ['Multimodal', 'Multimodal'],
                    ['Keypoints', 'Keypoints'],
                    ['NLP', 'NLP'],
                  ]}
                />
                <SelectField
                  label="分类标签"
                  value={newProjCategory}
                  onChange={setNewProjCategory}
                  options={[
                    ['Layout Analysis', 'Layout Analysis'],
                    ['Instance Segmentation', 'Instance Segmentation'],
                    ['Image-Text Align', 'Image-Text Align'],
                    ['Keypoints Detection', 'Keypoints Detection'],
                  ]}
                />
              </div>
              <div className="flex justify-end gap-3 border-t border-outline-variant/40 pt-4">
                <button type="button" onClick={() => setIsNewProjectModalOpen(false)} className="rounded-[0.75rem] border border-outline-variant/50 px-4 py-2 text-label-md font-semibold text-on-surface-variant hover:bg-surface-container">取消</button>
                <button type="submit" className="rounded-[0.75rem] bg-primary px-5 py-2 text-label-md font-semibold text-on-primary hover:bg-primary/90">创建</button>
              </div>
            </form>
          </Modal>
        )}

        {isCollaboratorsOpen && (
          <Modal title="团队成员" onClose={() => setIsCollaboratorsOpen(false)}>
            <div className="max-h-96 space-y-3 overflow-y-auto pr-1">
              {collaborators.map((collaborator) => (
                <div key={collaborator.id} className="flex items-center justify-between rounded-[0.75rem] border border-outline-variant/40 bg-surface-container p-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-label-md font-bold text-on-primary">
                      {initials(collaborator.name)}
                    </div>
                    <div>
                      <h3 className="text-label-md font-semibold text-primary">{collaborator.name}</h3>
                      <p className="text-label-sm text-on-surface-variant">{collaborator.role}</p>
                    </div>
                  </div>
                  <span className="rounded-full bg-primary/10 px-2 py-1 text-label-sm font-semibold text-primary">Active</span>
                </div>
              ))}
            </div>
          </Modal>
        )}

        {isEnterpriseModalOpen && (
          <Modal title="企业工作区说明" onClose={() => setIsEnterpriseModalOpen(false)}>
            <div className="space-y-4 text-label-md leading-6 text-on-surface-variant">
              {[
                '统一的页面外壳用于承载项目、数据集、提示词、设置和工作台入口。',
                '数据集处理结果会同步到项目列表，方便直接进入查看或标注。',
                '后续可以继续接入权限、任务分派和质量统计。'
              ].map((item) => (
                <div key={item} className="flex gap-2">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </Modal>
        )}
      </AnimatePresence>
    </section>
  );
}

function MetricCard({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-[1.5rem] border border-outline-variant/40 bg-surface/50 p-6 backdrop-blur-sm">
      <span className="text-label-md font-medium uppercase tracking-wider text-on-surface-variant">{label}</span>
      <div className="mt-3 text-display-lg font-bold leading-none text-primary">{value}</div>
      <p className="mt-3 text-label-sm font-semibold text-on-surface-variant">{note}</p>
    </div>
  );
}

function ProjectCard({ project, onSelect }: { project: Project; onSelect: () => void }) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect();
        }
      }}
      className="group flex h-full cursor-pointer gap-5 rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-6 transition-all hover:shadow-[0_8px_30px_rgba(0,0,0,0.04)] focus:outline-none focus:ring-2 focus:ring-primary/30"
    >
      <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-[0.75rem] bg-surface-container-high text-primary">
        <FileText className="h-9 w-9" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="rounded bg-surface-container px-2 py-0.5 text-label-sm font-semibold text-primary">{project.type}</span>
          <span className="text-label-sm font-semibold text-on-surface-variant">{project.category}</span>
        </div>
        <h3 className="truncate text-headline-sm font-semibold text-primary">{project.name}</h3>
        <p className="mt-2 line-clamp-2 text-label-md leading-6 text-on-surface-variant">{project.description}</p>
        <div className="mt-5">
          <div className="mb-2 flex justify-between text-label-sm font-semibold text-on-surface-variant">
            <span>完成进度</span>
            <span>{project.progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-container-high">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${project.progress}%` }} />
          </div>
        </div>
      </div>
    </article>
  );
}

function EmptyState({ title, description, actionLabel, onAction }: { title: string; description: string; actionLabel: string; onAction: () => void }) {
  return (
    <div className="rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-[40px] text-center">
      <Database className="mx-auto mb-4 h-10 w-10 text-on-surface-variant" />
      <h3 className="text-headline-sm font-semibold text-primary">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-body-md text-on-surface-variant">{description}</p>
      <button onClick={onAction} className="mt-5 rounded-[0.75rem] bg-primary px-5 py-3 text-label-md font-semibold text-on-primary hover:bg-primary/90">
        {actionLabel}
      </button>
    </div>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.98, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 10 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        className="w-full max-w-lg rounded-[1.5rem] border border-outline-variant/60 bg-surface-container-lowest p-6 shadow-[0_24px_80px_rgba(0,0,0,0.12)]"
      >
        <div className="mb-6 flex items-center justify-between gap-4">
          <h2 className="text-headline-sm font-semibold text-primary">{title}</h2>
          <button onClick={onClose} className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container" aria-label="关闭">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </motion.div>
    </div>
  );
}

function Field({ label, value, onChange, required, placeholder }: { label: string; value: string; onChange: (value: string) => void; required?: boolean; placeholder?: string }) {
  return (
    <label className="block text-label-sm font-semibold text-on-surface-variant">
      {label}
      <input
        value={value}
        required={required}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-label-md text-on-surface outline-none placeholder:text-on-surface-variant focus:border-primary"
      />
    </label>
  );
}

function Textarea({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <label className="block text-label-sm font-semibold text-on-surface-variant">
      {label}
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={3}
        className="mt-1 w-full resize-none rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-label-md text-on-surface outline-none placeholder:text-on-surface-variant focus:border-primary"
      />
    </label>
  );
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) {
  return (
    <label className="block text-label-sm font-semibold text-on-surface-variant">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-label-md text-on-surface outline-none focus:border-primary"
      >
        {options.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>
    </label>
  );
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}
