import React, { useMemo, useState } from 'react';
import {
  Bell,
  Boxes,
  BriefcaseBusiness,
  ChevronDown,
  CircleHelp,
  Clock3,
  Database,
  FileText,
  Filter,
  FolderOpen,
  Grid2X2,
  Image,
  LogOut,
  Menu,
  Plus,
  Search,
  UserCircle,
  Wrench
} from 'lucide-react';
import { BackendJobSummary } from '../types';

interface DatasetsPageProps {
  jobs: BackendJobSummary[];
  onNavigate: (tab: 'projects' | 'datasets' | 'analytics' | 'team' | 'settings') => void;
}

type DatasetCategory = 'All' | 'PDF Layout' | 'Completed' | 'Running' | 'Error';
type DatasetStatus = 'Completed' | 'Running' | 'Error';

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
}

export default function DatasetsPage({ jobs, onNavigate }: DatasetsPageProps) {
  const [activeCategory, setActiveCategory] = useState<DatasetCategory>('All');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | DatasetStatus>('All');

  const datasets = useMemo(() => jobs.map(mapJobToDataset), [jobs]);

  const totalPages = useMemo(() => jobs.reduce((sum, job) => sum + (job.page_count || 0), 0), [jobs]);
  const totalBlocks = useMemo(() => jobs.reduce((sum, job) => sum + (job.block_count || 0), 0), [jobs]);
  const completedCount = useMemo(() => datasets.filter((dataset) => dataset.status === 'Completed').length, [datasets]);

  const filteredDatasets = useMemo(() => {
    return datasets.filter((dataset) => {
      const matchesCategory = activeCategory === 'All' || activeCategory === 'PDF Layout' || dataset.status === activeCategory;
      const matchesStatus = statusFilter === 'All' || dataset.status === statusFilter;
      const haystack = `${dataset.name} ${dataset.category} ${dataset.amountLabel} ${dataset.model} ${dataset.templateName || ''}`.toLowerCase();
      return matchesCategory && matchesStatus && haystack.includes(searchTerm.toLowerCase());
    });
  }, [activeCategory, datasets, searchTerm, statusFilter]);

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
                  <button className="rounded-[0.75rem] border border-primary bg-surface-container-lowest px-6 py-3 text-label-md font-medium text-primary transition-colors hover:bg-surface-container active:scale-[0.98]">
                    Import Data
                  </button>
                  <button className="flex items-center gap-2 rounded-[0.75rem] bg-primary px-6 py-3 text-label-md font-medium text-on-primary shadow-sm transition-colors hover:bg-primary/90 active:scale-[0.98]">
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
                  {(['All', 'PDF Layout', 'Completed', 'Running', 'Error'] as DatasetCategory[]).map((category) => (
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

              {filteredDatasets.length > 0 ? (
                <div className="relative z-10 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {filteredDatasets.map((dataset) => (
                    <React.Fragment key={dataset.id}>
                      <DatasetCard dataset={dataset} />
                    </React.Fragment>
                  ))}
                </div>
              ) : (
                <div className="relative z-10 rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-[40px] text-center">
                  <Database className="mx-auto mb-4 h-10 w-10 text-on-surface-variant" />
                  <h3 className="text-headline-sm font-semibold text-primary">No backend datasets found</h3>
                  <p className="mx-auto mt-2 max-w-md text-body-md text-on-surface-variant">
                    Run a PDF analysis from the annotation workspace and the generated dataset records will appear here.
                  </p>
                </div>
              )}
            </section>
          </div>
        </main>
      </div>
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

function DatasetCard({ dataset }: { dataset: DatasetItem }) {
  const isError = dataset.status === 'Error';

  return (
    <article className="group flex h-full cursor-pointer flex-col rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-[32px] transition-all duration-300 hover:shadow-[0_8px_30px_rgba(0,0,0,0.04)] active:scale-[0.98]">
      <div className="mb-6 flex items-start justify-between">
        <div className={`flex h-12 w-12 items-center justify-center rounded-[0.75rem] bg-surface-container-high text-primary transition-colors group-hover:bg-primary group-hover:text-surface-container-lowest ${isError ? 'opacity-60' : ''}`}>
          {iconForDataset(dataset.icon)}
        </div>
        <StatusBadge status={dataset.status} />
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
          <p className={`mb-3 flex items-center gap-1 text-label-sm font-semibold ${isError ? 'text-on-surface-variant/50' : 'text-on-surface-variant/70'}`}>
            <Clock3 className="h-3.5 w-3.5" />
            {dataset.updated}
          </p>
        )}
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

  return {
    id: job.job_id,
    name: job.filename || `Dataset ${job.job_id}`,
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
