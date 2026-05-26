import React, { useMemo, useState } from 'react';
import {
  Bell,
  Boxes,
  BriefcaseBusiness,
  ChevronDown,
  CircleHelp,
  Clock3,
  Database,
  Download,
  FileText,
  Filter,
  FolderOpen,
  Grid2X2,
  Image,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  SquareCheckBig,
  Trash2,
  UserCircle,
  Wrench,
  X
} from 'lucide-react';
import { AnnotationFeature, BackendJobSummary } from '../types';
import { motion, AnimatePresence } from 'motion/react';

interface DatasetsPageProps {
  jobs: BackendJobSummary[];
  onNavigate: (tab: 'projects' | 'datasets' | 'prompts' | 'analytics' | 'team' | 'settings') => void;
  onCreateDataset: (feature: AnnotationFeature) => void;
  onOpenDataset: (jobId: string) => void;
  onSecondAnnotate: (datasetId: string) => void;
  onRefreshDatasets: () => void;
}

type DatasetCategory = 'All' | '一次标注' | '已二次标注' | 'ms-swift' | 'Completed' | 'Running' | 'Error';
type DatasetStatus = 'Completed' | 'Running' | 'Error';
type TargetFormat = 'llamafactory' | 'swift';
type SplitType = 'train' | 'val' | 'test' | 'all';

interface DatasetItem {
  id: string;
  name: string;
  category: 'PDF Layout';
  amount: string;
  amountLabel: string;
  status: DatasetStatus;
  updated: string;
  icon: 'image' | 'box' | 'notes' | 'error';
  progress?: number;
  progressLabel?: string;
  blockCount: number;
  pageCount: number;
  model: string;
  templateName?: string;
  annotationStatus: BackendJobSummary['annotation_status'];
  convertStatus: BackendJobSummary['convert_status'];
  convertError?: string;
  convertedFormats: string[];
  firstAnnotatedAt?: number | null;
  secondAnnotatedAt?: number | null;
  lastConvertPath?: string;
  lastConvertFormat?: string;
}

const DATASET_TYPE_OPTIONS: Array<{
  id: AnnotationFeature;
  label: string;
  description: string;
  status: 'available' | 'pending';
}> = [
  {
    id: 'layout',
    label: '版面分析标注',
    description: '上传 PDF 后调用现有后端版面分析服务，并进入结果浏览与修正工作台。',
    status: 'available',
  },
  {
    id: 'bounding_box',
    label: '目标框标注',
    description: '待开发',
    status: 'pending',
  },
  {
    id: 'polygon',
    label: '多边形分割',
    description: '待开发',
    status: 'pending',
  },
  {
    id: 'keypoints',
    label: '关键点标注',
    description: '待开发',
    status: 'pending',
  },
  {
    id: 'text_transcription',
    label: '文字转录标注',
    description: '待开发',
    status: 'pending',
  },
];

export default function DatasetsPage({ jobs, onNavigate, onCreateDataset, onOpenDataset, onSecondAnnotate, onRefreshDatasets }: DatasetsPageProps) {
  const [activeCategory, setActiveCategory] = useState<DatasetCategory>('All');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | DatasetStatus>('All');
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [convertDialog, setConvertDialog] = useState<{ open: boolean; targetFormat: TargetFormat }>({ open: false, targetFormat: 'llamafactory' });
  const [mergeDatasets, setMergeDatasets] = useState(true);
  const [splitType, setSplitType] = useState<SplitType>('train');
  const [overwriteOutput, setOverwriteOutput] = useState(false);
  const [outputName, setOutputName] = useState(defaultOutputName('llamafactory', true));
  const [convertMessage, setConvertMessage] = useState('');
  const [convertError, setConvertError] = useState('');
  const [isConverting, setIsConverting] = useState(false);

  const datasets = useMemo(() => jobs.map(mapJobToDataset), [jobs]);

  const totalPages = useMemo(() => jobs.reduce((sum, job) => sum + (job.page_count || 0), 0), [jobs]);
  const totalBlocks = useMemo(() => jobs.reduce((sum, job) => sum + (job.block_count || 0), 0), [jobs]);
  const completedCount = useMemo(() => datasets.filter((dataset) => dataset.status === 'Completed').length, [datasets]);
  const selectedDatasets = useMemo(() => datasets.filter((dataset) => selectedIds.includes(dataset.id)), [datasets, selectedIds]);

  const filteredDatasets = useMemo(() => {
    return datasets.filter((dataset) => {
      const matchesCategory =
        activeCategory === 'All'
        || (activeCategory === '一次标注' && dataset.annotationStatus === 'first_annotated')
        || (activeCategory === '已二次标注' && dataset.annotationStatus === 'second_annotated')
        || (activeCategory === 'ms-swift' && hasSwiftConversion(dataset))
        || dataset.status === activeCategory;
      const matchesStatus = statusFilter === 'All' || dataset.status === statusFilter;
      const haystack = `${dataset.name} ${dataset.category} ${dataset.amountLabel} ${dataset.model} ${dataset.templateName || ''}`.toLowerCase();
      return matchesCategory && matchesStatus && haystack.includes(searchTerm.toLowerCase());
    });
  }, [activeCategory, datasets, searchTerm, statusFilter]);

  function toggleSelection(dataset: DatasetItem) {
    setConvertError('');
    setSelectedIds((current) => current.includes(dataset.id) ? current.filter((id) => id !== dataset.id) : [...current, dataset.id]);
  }

  async function deleteSelectedDatasets() {
    if (selectedIds.length === 0) {
      setConvertError('请先选择要删除的数据集。');
      return;
    }
    if (!window.confirm(`确认删除已选择的 ${selectedIds.length} 个数据集吗？该操作会删除一次标注和二次标注文件。`)) return;
    await deleteDatasets({ dataset_ids: selectedIds });
  }

  async function deleteAllDatasets() {
    if (datasets.length === 0) {
      setConvertError('当前没有可删除的数据集。');
      return;
    }
    if (!window.confirm(`确认删除全部 ${datasets.length} 个数据集吗？该操作会清空当前数据集列表中的一次标注和二次标注文件。`)) return;
    await deleteDatasets({ delete_all: true });
  }

  async function deleteDatasets(payload: { dataset_ids?: string[]; delete_all?: boolean }) {
    try {
      setConvertError('');
      setConvertMessage('正在删除数据集...');
      const response = await fetch('/api/datasets/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.error) throw new Error(result.error || `HTTP ${response.status}`);
      setSelectedIds([]);
      setConvertMessage(`已删除 ${result.count || 0} 个数据集${result.failed?.length ? `，失败 ${result.failed.length} 个：${result.failed.map((item: { dataset_id: string; error: string }) => `${item.dataset_id} ${item.error}`).join('；')}` : ''}`);
      onRefreshDatasets();
    } catch (error) {
      setConvertError(error instanceof Error ? error.message : String(error));
    }
  }

  function openConvertDialog(targetFormat: TargetFormat) {
    const invalid = selectedDatasets.filter((dataset) => !isConvertible(dataset));
    if (selectedDatasets.length === 0) {
      setConvertError('请先选择至少一个已处理或已标注完成的数据集。');
      return;
    }
    if (invalid.length) {
      setConvertError(`以下数据集不可转换：${invalid.map((item) => item.name).join('、')}`);
      return;
    }
    setConvertError('');
    setConvertDialog({ open: true, targetFormat });
    setOutputName(defaultOutputName(targetFormat, mergeDatasets || selectedDatasets.length > 1));
  }

  async function startConvert() {
    try {
      setIsConverting(true);
      setConvertError('');
      setConvertMessage('转换任务已提交，正在处理...');
      const response = await fetch('/api/datasets/convert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_ids: selectedIds,
          target_format: convertDialog.targetFormat,
          merge: mergeDatasets,
          split_type: splitType,
          output_name: outputName.trim() || defaultOutputName(convertDialog.targetFormat, mergeDatasets),
          overwrite: overwriteOutput,
        }),
      });
      const task = await response.json();
      if (!response.ok || task.error) throw new Error(task.error || `HTTP ${response.status}`);
      await pollConvertTask(task.task_id);
    } catch (error) {
      setIsConverting(false);
      setConvertError(error instanceof Error ? error.message : String(error));
    }
  }

  async function pollConvertTask(taskId: string) {
    for (let i = 0; i < 120; i += 1) {
      const response = await fetch(`/api/datasets/convert/${taskId}`, { cache: 'no-store' });
      const task = await response.json();
      if (!response.ok || task.error) throw new Error(task.error || `HTTP ${response.status}`);
      if (task.status !== 'converting') {
        setIsConverting(false);
        setConvertDialog((current) => ({ ...current, open: false }));
        setConvertMessage(`${statusText(task.status)}：${task.output_path || ''}${task.skipped_samples ? `，跳过 ${task.skipped_samples} 条异常样本` : ''}`);
        if (task.status === 'failed') setConvertError(task.error || '转换失败');
        if (convertDialog.targetFormat === 'swift' && (task.status === 'success' || task.status === 'partial_success')) {
          setActiveCategory('ms-swift');
        }
        onRefreshDatasets();
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    throw new Error('转换任务超时，请稍后刷新状态。');
  }

  return (
    <div className="min-h-full w-full overflow-hidden bg-surface-container-low text-primary font-['Inter']">
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-[400px] bg-gradient-to-t from-on-tertiary-container/10 via-primary/5 to-transparent blur-[120px]" />

      <nav className="sticky top-0 z-50 mx-auto flex h-16 w-full max-w-[1920px] items-center justify-between border-b border-outline-variant/30 bg-surface/80 px-container-desktop backdrop-blur-xl">
        <div className="flex items-center gap-8">
          <button onClick={() => onNavigate('projects')} className="text-headline-md font-bold tracking-tight text-primary active:scale-95 transition-transform">
            MarkHub
          </button>
          <div className="hidden items-center gap-6 md:flex">
            <TopNavButton label="Projects" active={false} onClick={() => onNavigate('projects')} />
            <TopNavButton label="Datasets" active onClick={() => onNavigate('datasets')} />
            <TopNavButton label="Prompts" active={false} onClick={() => onNavigate('prompts')} />
            <TopNavButton label="Analytics" active={false} onClick={() => onNavigate('analytics')} />
            <TopNavButton label="Team" active={false} onClick={() => onNavigate('team')} />
            <TopNavButton label="Settings" active={false} onClick={() => onNavigate('settings')} />
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="relative hidden lg:block">
            <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-on-surface-variant" />
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              className="h-12 w-80 rounded-full border border-outline-variant/50 bg-surface-container py-2 pl-10 pr-4 text-body-md text-on-surface-variant outline-none transition-colors focus:border-primary focus:ring-0"
              placeholder="Search datasets..."
              type="search"
            />
          </div>
          <button className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary active:scale-95" aria-label="Notifications">
            <Bell className="h-6 w-6" />
          </button>
          <button className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary active:scale-95" aria-label="Account">
            <UserCircle className="h-6 w-6" />
          </button>
        </div>
      </nav>

      <div className="mx-auto flex max-w-[1920px]">
        <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-64 shrink-0 flex-col gap-4 border-r border-outline-variant/30 bg-surface p-gutter md:flex">
          <div className="mb-4 flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border border-outline-variant/30 bg-surface-container-high text-primary">
              <BriefcaseBusiness className="h-5 w-5" />
            </div>
            <div>
              <div className="w-40 truncate text-label-md font-bold text-primary">Enterprise Workspace</div>
              <div className="text-label-sm font-semibold text-on-surface-variant">Data Science Lab</div>
            </div>
          </div>

          <div className="flex flex-1 flex-col gap-2">
            <SideNavButton icon={<Grid2X2 className="h-5 w-5" />} label="Dashboard" />
            <SideNavButton icon={<FileText className="h-5 w-5" />} label="Tasks" />
            <SideNavButton icon={<Wrench className="h-5 w-5" />} label="Tools" />
            <SideNavButton icon={<CircleHelp className="h-5 w-5" />} label="Help" />
          </div>

          <div className="mt-auto border-t border-outline-variant/30 pt-4">
            <SideNavButton icon={<LogOut className="h-5 w-5" />} label="Log out" />
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-gutter md:p-[40px]">
          <div className="mx-auto max-w-7xl space-y-[40px]">
            <section className="relative overflow-hidden rounded-[1.5rem] border border-surface-variant bg-surface-container-lowest p-[32px] shadow-[0_20px_50px_rgba(0,0,0,0.02)] md:p-[40px]">
              <div className="relative z-10 mb-12 flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
                <div>
                  <h1 className="text-headline-lg font-semibold tracking-[-0.01em] text-primary">Datasets</h1>
                  <p className="mt-2 text-body-md text-on-surface-variant">Manage and process your core data infrastructure.</p>
                </div>
                <div className="flex w-full flex-wrap items-center gap-4 md:w-auto">
                  <div className="relative w-full md:w-auto lg:hidden">
                    <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-on-surface-variant" />
                    <input
                      value={searchTerm}
                      onChange={(event) => setSearchTerm(event.target.value)}
                      className="h-12 w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container py-3 pl-10 pr-4 text-body-md outline-none transition-colors focus:border-primary focus:ring-0"
                      placeholder="Search datasets..."
                      type="search"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => openConvertDialog('llamafactory')}
                    className="flex items-center gap-2 rounded-[0.75rem] border border-primary bg-surface-container-lowest px-5 py-3 text-label-md font-medium text-primary transition-colors hover:bg-surface-container active:scale-[0.98]"
                  >
                    <Download className="h-[18px] w-[18px]" />
                    LLaMA-Factory
                  </button>
                  <button
                    type="button"
                    onClick={() => openConvertDialog('swift')}
                    className="flex items-center gap-2 rounded-[0.75rem] border border-primary bg-surface-container-lowest px-5 py-3 text-label-md font-medium text-primary transition-colors hover:bg-surface-container active:scale-[0.98]"
                  >
                    <Download className="h-[18px] w-[18px]" />
                    ms-swift
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsCreateDialogOpen(true)}
                    className="flex items-center gap-2 rounded-[0.75rem] bg-primary px-6 py-3 text-label-md font-medium text-on-primary shadow-sm transition-colors hover:bg-primary/90 active:scale-[0.98]"
                  >
                    <Plus className="h-[18px] w-[18px]" />
                    Create New Dataset
                  </button>
                </div>
              </div>

              <div className="relative z-10 mb-12 grid grid-cols-1 gap-6 md:grid-cols-3">
                <KpiCard label="Total Datasets" value={formatCount(jobs.length)} />
                <KpiCard label="Total Pages" value={formatCount(totalPages)} />
                <div className="relative flex flex-col gap-2 overflow-hidden rounded-[1.5rem] border border-outline-variant/40 bg-surface/50 p-6 backdrop-blur-sm">
                  <span className="text-label-md font-medium uppercase tracking-wider text-on-surface-variant">Layout Blocks</span>
                  <div className="flex items-baseline gap-2">
                    <span className="text-display-lg font-bold tracking-[-0.02em] text-primary">{formatCount(totalBlocks)}</span>
                    <span className="text-headline-md font-semibold text-on-surface-variant">blocks</span>
                  </div>
                  <div className="absolute bottom-0 left-0 h-1 w-full bg-surface-container-highest">
                    <div className="h-full bg-primary" style={{ width: `${jobs.length ? Math.round((completedCount / jobs.length) * 100) : 0}%` }} />
                  </div>
                </div>
              </div>

              <div className="relative z-10 mb-8 flex flex-col items-center justify-between gap-4 border-b border-surface-variant pb-4 md:flex-row">
                <div className="flex w-full gap-6 overflow-x-auto md:w-auto">
                  {(['All', '一次标注', '已二次标注', 'ms-swift', 'Completed', 'Running', 'Error'] as DatasetCategory[]).map((category) => (
                    <button
                      key={category}
                      onClick={() => setActiveCategory(category)}
                      className={`whitespace-nowrap pb-2 text-label-md font-medium transition-colors ${
                        activeCategory === category
                          ? 'border-b-2 border-primary font-bold text-primary'
                          : 'text-on-surface-variant hover:text-primary'
                      }`}
                    >
                      {category}
                    </button>
                  ))}
                </div>
                <div className="flex w-full justify-end md:w-auto">
                  <div className="mr-3 flex items-center gap-2 text-label-sm font-semibold text-on-surface-variant">
                    <SquareCheckBig className="h-4 w-4" />
                    已选择 {selectedIds.length}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const visibleIds = filteredDatasets.map((dataset) => dataset.id);
                      const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
                      setSelectedIds(allVisibleSelected ? [] : visibleIds);
                    }}
                    className="mr-2 flex items-center gap-2 rounded-[0.75rem] border border-outline-variant/50 px-3 py-2 text-label-md font-medium text-on-surface-variant transition-colors hover:bg-surface-container active:scale-[0.98]"
                  >
                    {filteredDatasets.length > 0 && filteredDatasets.every((dataset) => selectedIds.includes(dataset.id)) ? '取消全选' : '全选当前'}
                  </button>
                  <button
                    type="button"
                    onClick={deleteSelectedDatasets}
                    disabled={selectedIds.length === 0}
                    className="mr-2 flex items-center gap-2 rounded-[0.75rem] border border-error/30 px-3 py-2 text-label-md font-medium text-error transition-colors hover:bg-error/10 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Trash2 className="h-[18px] w-[18px]" />
                    删除所选
                  </button>
                  <button
                    type="button"
                    onClick={deleteAllDatasets}
                    disabled={datasets.length === 0}
                    className="mr-2 flex items-center gap-2 rounded-[0.75rem] border border-error/30 px-3 py-2 text-label-md font-medium text-error transition-colors hover:bg-error/10 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    全部删除
                  </button>
                  <button
                    type="button"
                    onClick={onRefreshDatasets}
                    className="mr-2 flex items-center gap-2 rounded-[0.75rem] border border-outline-variant/50 px-3 py-2 text-label-md font-medium text-on-surface-variant transition-colors hover:bg-surface-container active:scale-[0.98]"
                  >
                    <RefreshCw className="h-[18px] w-[18px]" />
                  </button>
                  <button
                    onClick={() => setStatusFilter(statusFilter === 'All' ? 'Completed' : statusFilter === 'Completed' ? 'Running' : statusFilter === 'Running' ? 'Error' : 'All')}
                    className="flex items-center gap-2 rounded-[0.75rem] border border-outline-variant/50 px-4 py-2 text-label-md font-medium text-on-surface-variant transition-colors hover:bg-surface-container active:scale-[0.98]"
                  >
                    <Filter className="h-[18px] w-[18px]" />
                    Status: {statusFilter}
                    <ChevronDown className="h-[18px] w-[18px]" />
                  </button>
                </div>
              </div>

              {(convertError || convertMessage) && (
                <div className={`relative z-10 mb-6 rounded-[0.75rem] border px-4 py-3 text-label-md font-semibold ${convertError ? 'border-error/20 bg-error/10 text-error' : 'border-primary/20 bg-primary/10 text-primary'}`}>
                  {convertError || convertMessage}
                </div>
              )}

              {filteredDatasets.length > 0 ? (
                <div className="relative z-10 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {filteredDatasets.map((dataset) => (
                    <React.Fragment key={dataset.id}>
                      <DatasetCard
                        dataset={dataset}
                        selected={selectedIds.includes(dataset.id)}
                        onToggleSelected={() => toggleSelection(dataset)}
                        onOpen={() => onOpenDataset(dataset.id)}
                        onSecondAnnotate={() => onSecondAnnotate(dataset.id)}
                        onConvert={() => {
                          if (!isConvertible(dataset)) {
                            setConvertError(`「${dataset.name}」当前状态不可转换，请选择已处理或已标注完成的数据集。`);
                            return;
                          }
                          setSelectedIds([dataset.id]);
                          setConvertDialog({ open: true, targetFormat: 'swift' });
                          setOutputName(defaultOutputName('swift', false));
                        }}
                      />
                    </React.Fragment>
                  ))}
                </div>
              ) : (
                <div className="relative z-10 rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-[40px] text-center">
                  <Database className="mx-auto mb-4 h-10 w-10 text-on-surface-variant" />
                  <h3 className="text-headline-sm font-semibold text-primary">{activeCategory === 'ms-swift' ? 'No ms-swift conversions found' : 'No backend datasets found'}</h3>
                  <p className="mx-auto mt-2 max-w-md text-body-md text-on-surface-variant">
                    {activeCategory === 'ms-swift'
                      ? '选择一次标注完成的数据集，点击 ms-swift 转换后，转换结果会出现在这个列表中。'
                      : 'Run a PDF analysis from the annotation workspace and the generated dataset records will appear here.'}
                  </p>
                </div>
              )}
            </section>
          </div>
        </main>
      </div>

      <AnimatePresence>
        {convertDialog.open && (
          <div className="fixed inset-0 z-[75] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="w-full max-w-2xl rounded-[1.5rem] border border-outline-variant/60 bg-surface-container-lowest p-6 shadow-[0_24px_80px_rgba(0,0,0,0.12)]"
            >
              <div className="mb-5 flex items-start justify-between">
                <div>
                  <h2 className="text-headline-md font-semibold text-primary">转换配置</h2>
                  <p className="mt-1 text-body-md text-on-surface-variant">目标格式：{convertDialog.targetFormat === 'swift' ? 'ms-swift' : 'LLaMA-Factory'}</p>
                </div>
                <button onClick={() => setConvertDialog((current) => ({ ...current, open: false }))} className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container" aria-label="Close convert dialog">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="mb-4 max-h-36 overflow-y-auto rounded-[0.75rem] border border-outline-variant/50 bg-surface-container p-3">
                {selectedDatasets.map((dataset) => (
                  <div key={dataset.id} className="flex items-center justify-between py-1 text-label-md">
                    <span className="font-semibold text-primary">{dataset.name}</span>
                    <span className="text-on-surface-variant">{annotationStatusText(dataset.annotationStatus)}</span>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <label className="space-y-1 text-label-md font-semibold text-primary">
                  <span>输出目录名称</span>
                  <input value={outputName} onChange={(event) => setOutputName(event.target.value)} className="w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2 text-body-md outline-none focus:border-primary" />
                </label>
                <label className="space-y-1 text-label-md font-semibold text-primary">
                  <span>数据用途</span>
                  <select value={splitType} onChange={(event) => setSplitType(event.target.value as SplitType)} className="w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2 text-body-md outline-none focus:border-primary">
                    <option value="train">train</option>
                    <option value="val">val</option>
                    <option value="test">test</option>
                    <option value="all">all</option>
                  </select>
                </label>
                <label className="flex items-center gap-3 rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2 text-label-md font-semibold text-primary">
                  <input type="checkbox" checked={mergeDatasets} onChange={(event) => setMergeDatasets(event.target.checked)} className="accent-current" />
                  合并多个数据集
                </label>
                <label className="flex items-center gap-3 rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2 text-label-md font-semibold text-primary">
                  <input type="checkbox" checked={overwriteOutput} onChange={(event) => setOverwriteOutput(event.target.checked)} className="accent-current" />
                  覆盖已有同名目录
                </label>
              </div>
              <div className="mt-6 flex justify-end gap-3">
                <button onClick={() => setConvertDialog((current) => ({ ...current, open: false }))} className="rounded-[0.75rem] border border-outline-variant/50 px-4 py-2 text-label-md font-semibold text-on-surface-variant hover:bg-surface-container">取消</button>
                <button onClick={startConvert} disabled={isConverting} className="rounded-[0.75rem] bg-primary px-4 py-2 text-label-md font-semibold text-on-primary hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60">
                  {isConverting ? '转换中...' : '开始转换'}
                </button>
              </div>
            </motion.div>
          </div>
        )}
        {isCreateDialogOpen && (
          <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="w-full max-w-2xl rounded-[1.5rem] border border-outline-variant/60 bg-surface-container-lowest p-6 shadow-[0_24px_80px_rgba(0,0,0,0.12)]"
            >
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-headline-md font-semibold text-primary">选择数据集制作类型</h2>
                  <p className="mt-2 text-body-md text-on-surface-variant">
                    当前平台已接入版面分析标注，其余数据集能力会按模块逐步开放。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsCreateDialogOpen(false)}
                  className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
                  aria-label="Close dataset type dialog"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="grid grid-cols-1 gap-3">
                {DATASET_TYPE_OPTIONS.map((option) => {
                  const available = option.status === 'available';
                  return (
                    <button
                      key={option.id}
                      type="button"
                      disabled={!available}
                      onClick={() => {
                        setIsCreateDialogOpen(false);
                        onCreateDataset(option.id);
                      }}
                      className={`flex items-center justify-between gap-4 rounded-[0.75rem] border p-4 text-left transition-all ${
                        available
                          ? 'border-primary bg-primary text-on-primary hover:bg-primary/90 active:scale-[0.99]'
                          : 'cursor-not-allowed border-outline-variant/50 bg-surface-container text-on-surface-variant opacity-70'
                      }`}
                    >
                      <span>
                        <span className="block text-label-md font-semibold">{option.label}</span>
                        <span className={`mt-1 block text-label-sm ${available ? 'text-on-primary/75' : 'text-on-surface-variant'}`}>
                          {option.description}
                        </span>
                      </span>
                      <span className={`shrink-0 rounded-full px-2.5 py-1 text-label-sm font-semibold ${available ? 'bg-white/15 text-white' : 'bg-surface-container-high text-on-surface-variant'}`}>
                        {available ? '可用' : '待开发'}
                      </span>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TopNavButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`text-label-md font-medium transition-all duration-200 active:scale-95 ${
        active ? 'border-b-2 border-primary pb-1 font-bold text-primary' : 'text-on-surface-variant hover:text-primary'
      }`}
    >
      {label}
    </button>
  );
}

function SideNavButton({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <button className="flex items-center gap-3 rounded-[0.75rem] px-4 py-3 text-on-surface-variant transition-all duration-200 hover:bg-surface-container-high active:scale-[0.98]">
      {icon}
      <span className="text-label-md font-medium">{label}</span>
    </button>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[1.5rem] border border-outline-variant/40 bg-surface/50 p-6 backdrop-blur-sm">
      <span className="text-label-md font-medium uppercase tracking-wider text-on-surface-variant">{label}</span>
      <span className="text-display-lg font-bold tracking-[-0.02em] text-primary">{value}</span>
    </div>
  );
}

function DatasetCard({
  dataset,
  selected,
  onToggleSelected,
  onOpen,
  onSecondAnnotate,
  onConvert,
}: {
  dataset: DatasetItem;
  selected: boolean;
  onToggleSelected: () => void;
  onOpen: () => void;
  onSecondAnnotate: () => void;
  onConvert: () => void;
}) {
  const isError = dataset.status === 'Error';
  const canSecondAnnotate = dataset.status === 'Completed' && ['first_annotated', 'second_annotated'].includes(dataset.annotationStatus || '');

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen();
        }
      }}
      className="group flex h-full cursor-pointer flex-col rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-[32px] transition-all duration-300 hover:shadow-[0_8px_30px_rgba(0,0,0,0.04)] focus:outline-none focus:ring-2 focus:ring-primary/30 active:scale-[0.98]"
    >
      <div className="mb-6 flex items-start justify-between">
        <div className={`flex h-12 w-12 items-center justify-center rounded-[0.75rem] bg-surface-container-high text-primary transition-colors group-hover:bg-primary group-hover:text-surface-container-lowest ${isError ? 'opacity-60' : ''}`}>
          {iconForDataset(dataset.icon)}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={selected}
            onClick={(event) => event.stopPropagation()}
            onChange={onToggleSelected}
            className="h-4 w-4 accent-primary"
            aria-label={`Select ${dataset.name}`}
          />
          <StatusBadge status={dataset.status} />
        </div>
      </div>

      <h3 className={`mb-2 text-headline-md font-semibold leading-8 ${isError ? 'text-on-surface-variant' : 'text-primary'}`}>
        {dataset.name}
      </h3>

      <div className="mb-6 flex items-center gap-3">
        <span className={`rounded bg-surface-container px-2 py-0.5 text-label-sm font-semibold ${isError ? 'text-on-surface-variant opacity-80' : 'text-primary'}`}>
          {dataset.category}
        </span>
        <span className={`flex items-center gap-1 text-label-sm font-semibold ${isError ? 'text-on-surface-variant/70' : 'text-on-surface-variant'}`}>
          <FolderOpen className="h-3.5 w-3.5" />
          {dataset.amount} {dataset.amountLabel}
        </span>
      </div>

      <div className="mb-6 space-y-1 text-label-sm font-semibold text-on-surface-variant/70">
        <p>{dataset.blockCount} layout blocks</p>
        <p>{dataset.model}</p>
        {dataset.templateName && <p>{dataset.templateName}</p>}
        <p>标注阶段：{annotationStatusText(dataset.annotationStatus)}</p>
        <p>转换状态：{convertStatusText(dataset.convertStatus)}</p>
        {dataset.convertedFormats.length > 0 && <p>格式：{dataset.convertedFormats.map(formatLabel).join(', ')}</p>}
        {dataset.lastConvertPath && (
          <p className="truncate" title={dataset.lastConvertPath}>
            输出目录：{dataset.lastConvertPath}
          </p>
        )}
        {dataset.convertError && <p className="text-error">错误：{dataset.convertError}</p>}
      </div>

      <div className="mt-auto">
        {dataset.progress !== undefined ? (
          <>
            <div className="mb-3 h-3 w-full overflow-hidden rounded-full bg-surface-container-high">
              <div className="h-full rounded-full bg-gradient-to-r from-on-tertiary-container to-primary" style={{ width: `${dataset.progress}%` }} />
            </div>
            <div className="flex justify-between text-label-sm font-semibold text-on-surface-variant">
              <span>{dataset.progressLabel}</span>
              <span>{dataset.progress}%</span>
            </div>
          </>
        ) : (
          <div className={`mb-3 space-y-1 text-label-sm font-semibold ${isError ? 'text-on-surface-variant/50' : 'text-on-surface-variant/70'}`}>
            <p className="flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" />{dataset.updated}</p>
            <p>一次标注：{formatTimestamp(dataset.firstAnnotatedAt)}</p>
            <p>二次标注：{formatTimestamp(dataset.secondAnnotatedAt)}</p>
          </div>
        )}
        <div className="grid grid-cols-3 gap-2 pt-2">
          <button type="button" onClick={(event) => { event.stopPropagation(); onOpen(); }} className="rounded bg-surface-container px-2 py-1.5 text-label-sm font-semibold text-primary hover:bg-surface-container-high">查看</button>
          <button type="button" disabled={!canSecondAnnotate} onClick={(event) => { event.stopPropagation(); onSecondAnnotate(); }} className="rounded bg-surface-container px-2 py-1.5 text-label-sm font-semibold text-primary hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-40">二次标注</button>
          <button type="button" disabled={!isConvertible(dataset)} onClick={(event) => { event.stopPropagation(); onConvert(); }} className="rounded bg-surface-container px-2 py-1.5 text-label-sm font-semibold text-primary hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-40">转换</button>
        </div>
      </div>
    </article>
  );
}

function StatusBadge({ status }: { status: DatasetStatus }) {
  if (status === 'Running') {
    return (
      <span className="flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-label-sm font-semibold text-primary">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
        Running
      </span>
    );
  }

  return (
    <span className={`rounded-full px-2.5 py-1 text-label-sm font-semibold ${status === 'Error' ? 'border border-outline-variant/30 bg-surface-container text-on-surface-variant' : 'bg-surface-container-high text-on-surface-variant'}`}>
      {status}
    </span>
  );
}

function iconForDataset(icon: DatasetItem['icon']) {
  switch (icon) {
    case 'image':
      return <Image className="h-6 w-6" />;
    case 'box':
      return <Boxes className="h-6 w-6" />;
    case 'notes':
      return <Menu className="h-6 w-6" />;
    case 'error':
      return <CircleHelp className="h-6 w-6" />;
    default:
      return <Database className="h-6 w-6" />;
  }
}

function mapJobToDataset(job: BackendJobSummary): DatasetItem {
  const progress = job.page_count > 0 ? Math.round(((job.completed_pages || 0) / job.page_count) * 100) : 0;
  const status = normalizeStatus(job.status);
  const datasetId = job.dataset_id || job.job_id;

  return {
    id: datasetId,
    name: job.filename || `Dataset ${datasetId}`,
    category: 'PDF Layout',
    amount: formatCount(job.page_count || 0),
    amountLabel: (job.page_count || 0) === 1 ? 'page' : 'pages',
    status,
    updated: formatUpdatedAt(job.updated_at),
    icon: status === 'Error' ? 'error' : status === 'Running' ? 'box' : 'image',
    progress: status === 'Running' ? progress : undefined,
    progressLabel: status === 'Running' ? `${job.completed_pages || 0}/${job.page_count || 0} pages processed` : undefined,
    blockCount: job.block_count || 0,
    pageCount: job.page_count || 0,
    model: job.model || 'Unknown model',
    templateName: job.prompt_template?.name,
    annotationStatus: job.annotation_status || (status === 'Completed' ? 'first_annotated' : 'none'),
    convertStatus: job.convert_status || 'none',
    convertError: job.convert_error,
    convertedFormats: job.converted_formats || [],
    firstAnnotatedAt: job.first_annotated_at,
    secondAnnotatedAt: job.second_annotated_at,
    lastConvertPath: job.last_convert_record?.output_path,
    lastConvertFormat: job.last_convert_record?.target_format,
  };
}

function normalizeStatus(status: string): DatasetStatus {
  const normalized = status.toLowerCase();
  if (normalized === 'complete' || normalized === 'completed' || normalized === 'done') return 'Completed';
  if (normalized === 'error' || normalized === 'failed') return 'Error';
  return 'Running';
}

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function formatUpdatedAt(updatedAt?: number): string {
  if (!updatedAt) return 'Updated recently';
  const deltaSeconds = Math.max(0, Math.floor(Date.now() / 1000 - updatedAt));
  if (deltaSeconds < 60) return 'Updated just now';
  if (deltaSeconds < 3600) return `Updated ${Math.floor(deltaSeconds / 60)} minutes ago`;
  if (deltaSeconds < 86400) return `Updated ${Math.floor(deltaSeconds / 3600)} hours ago`;
  if (deltaSeconds < 2592000) return `Updated ${Math.floor(deltaSeconds / 86400)} days ago`;
  return new Date(updatedAt * 1000).toLocaleDateString('zh-CN');
}

function isConvertible(dataset: DatasetItem): boolean {
  return dataset.status === 'Completed' && ['first_annotated', 'second_annotated'].includes(dataset.annotationStatus || '');
}

function hasSwiftConversion(dataset: DatasetItem): boolean {
  return dataset.convertedFormats.some((format) => format === 'swift' || format === 'ms-swift') || dataset.lastConvertFormat === 'swift';
}

function formatLabel(format: string): string {
  if (format === 'swift') return 'ms-swift';
  if (format === 'llamafactory') return 'LLaMA-Factory';
  return format;
}

function annotationStatusText(status?: BackendJobSummary['annotation_status']): string {
  switch (status) {
    case 'second_annotated':
      return '已二次标注';
    case 'second_annotating':
      return '二次标注中';
    case 'first_annotated':
      return '一次标注完成';
    default:
      return '未标注';
  }
}

function convertStatusText(status?: BackendJobSummary['convert_status']): string {
  switch (status) {
    case 'converting':
      return '转换中';
    case 'success':
      return '转换成功';
    case 'failed':
      return '转换失败';
    case 'partial_success':
      return '部分成功';
    default:
      return '未转换';
  }
}

function statusText(status?: string): string {
  switch (status) {
    case 'success':
      return '转换成功';
    case 'partial_success':
      return '部分成功';
    case 'failed':
      return '转换失败';
    default:
      return status || '未知状态';
  }
}

function formatTimestamp(value?: number | null): string {
  if (!value) return '—';
  return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false });
}

function defaultOutputName(format: TargetFormat, merge: boolean): string {
  const now = new Date();
  const stamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    '_',
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ].join('');
  const prefix = merge ? 'merged_' : '';
  return `${prefix}${format === 'swift' ? 'swift' : 'llamafactory'}_${stamp}`;
}
