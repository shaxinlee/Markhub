/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  ArrowLeft,
  CloudLightning,
  Database,
  Download,
  Upload,
  Info,
  Play,
  Undo2,
  Redo2,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Trash2,
  Table,
  Image as ImageIcon,
  List,
  Code2,
  AlertTriangle,
  FileText,
  RefreshCw,
  Settings2
} from 'lucide-react';
import { Project, AnnotationSegment, BackendBlockType } from '../types';
import { motion, AnimatePresence } from 'motion/react';

interface WorkspaceProps {
  project: Project;
  onGoBack: () => void;
  onUpdateProjectProgress: (projectId: string, progress: number) => void;
  onIncreaseAnnotationsCount: (increment: number) => void;
}

interface PromptTemplateOption {
  id: string;
  name: string;
}

interface BackendConfig {
  base_url?: string;
  model?: string;
  has_api_key?: string;
  render_dpi?: string;
  max_pages?: string;
  qwen_preset?: string;
  qwen_width?: string;
  qwen_height?: string;
  prompt_template_id?: string;
  timeout?: string;
}

interface BackendBlock {
  id: string;
  text?: string;
  bbox: [number, number, number, number];
  page_id: number;
  block_type: BackendBlockType;
  weak_heading?: boolean;
  level?: 'H1' | 'H2' | 'H3' | null;
}

interface BackendPage {
  page_id: number;
  image_url: string;
  width: number;
  height: number;
  status?: string;
  blocks?: BackendBlock[];
  error?: string;
}

interface BackendJob {
  job_id: string;
  filename: string;
  status: string;
  page_count: number;
  completed_pages: number;
  pages: BackendPage[];
  result?: { blocks?: BackendBlock[]; [key: string]: unknown };
  warnings?: string[];
  errors?: string[];
  config?: { model?: string; base_url?: string; timeout?: string; model_dir?: string };
  resize?: { preset?: string; width?: number; height?: number };
  prompt_template?: PromptTemplateOption;
}

interface BackendJobSummary {
  job_id: string;
  filename: string;
  model?: string;
  status: string;
  page_count: number;
  completed_pages: number;
  block_count: number;
  error_count?: number;
  prompt_template?: PromptTemplateOption;
}

const BLOCK_TYPES: BackendBlockType[] = [
  'doc_title',
  'paragraph_title',
  'text',
  'table',
  'figure_title',
  'image',
  'vision_footnote'
];

const BLOCK_TYPE_LABELS: Record<BackendBlockType, string> = {
  doc_title: 'Doc Title',
  paragraph_title: 'Paragraph Title',
  text: 'Text',
  table: 'Table',
  figure_title: 'Figure Title',
  image: 'Image',
  vision_footnote: 'Footnote'
};

const DEFAULT_VISIBLE_TYPES: Record<BackendBlockType, boolean> = {
  doc_title: true,
  paragraph_title: true,
  text: true,
  table: true,
  figure_title: true,
  image: true,
  vision_footnote: true
};

export default function Workspace({
  project,
  onGoBack,
  onUpdateProjectProgress,
  onIncreaseAnnotationsCount
}: WorkspaceProps) {
  const [baseUrl, setBaseUrl] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [timeout, setTimeoutValue] = useState('180');
  const [renderDpi, setRenderDpi] = useState('180');
  const [maxPages, setMaxPages] = useState('50');
  const [qwenPreset, setQwenPreset] = useState('default');
  const [qwenWidth, setQwenWidth] = useState('1536');
  const [qwenHeight, setQwenHeight] = useState('2176');
  const [promptTemplateId, setPromptTemplateId] = useState('default_template_1');
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplateOption[]>([
    { id: 'default_template_1', name: '默认模板 1' }
  ]);
  const [targetElements, setTargetElements] = useState<Record<BackendBlockType, boolean>>(DEFAULT_VISIBLE_TYPES);

  const [activeTab, setActiveTab] = useState<'list' | 'json'>('list');
  const [scale, setScale] = useState<number>(0.9);
  const [documentImage, setDocumentImage] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [apiSource, setApiSource] = useState<'default' | 'backend'>('default');

  const [analysisJob, setAnalysisJob] = useState<BackendJob | null>(null);
  const [jobs, setJobs] = useState<BackendJobSummary[]>([]);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [segments, setSegments] = useState<AnnotationSegment[]>([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  const [history, setHistory] = useState<AnnotationSegment[][]>([]);
  const [historyPointer, setHistoryPointer] = useState<number>(-1);

  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [currentDragPos, setCurrentDragPos] = useState({ x: 0, y: 0 });
  const [newBoxModalOpen, setNewBoxModalOpen] = useState(false);
  const [drawnBoxPercent, setDrawnBoxPercent] = useState<[number, number, number, number] | null>(null);
  const [newBoxType, setNewBoxType] = useState<BackendBlockType>('text');
  const [newBoxText, setNewBoxText] = useState('');

  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentPage = analysisJob?.pages?.[currentPageIndex] || null;
  const displayedPageCount = analysisJob?.page_count || 0;
  const completedPages = analysisJob?.completed_pages || 0;
  const activeTemplateName = analysisJob?.prompt_template?.name || promptTemplates.find(t => t.id === promptTemplateId)?.name || '默认模板 1';

  useEffect(() => {
    const initImage = project.images && project.images.length > 0
      ? project.images[0]
      : 'https://lh3.googleusercontent.com/aida-public/AB6AXuA8Vg0FsccBPKY0Dqx1Qe7KlonM5GY3dxlAnmDJvmMl0XFhDW8jPgVY8gJEQqh2ca4NTw1tTMzgo8FNVlibPV0_P9ekG5UqCsGmyYCHBRgKN_JSndOr_BuOq2v8f3UK9TDMJTNnAjjAlvX2g2vQ9aHu07ce9mebXb-GWLu-OxKCJkacxAG-TiRIOv3Zy0lR3eI9T5fVoS7hhKfCE9v5pkuUJzDQtO4c8zyal1XqPLg7XvI0l-EZ7T-jxghtTDSQMUPEdmh0HLDnNDg';

    const initialMockSegments: AnnotationSegment[] = [
      { id: 'seg_1', type: 'doc_title', box: [10, 10, 80, 8], text: 'Q3 Enterprise Solutions Strategy Proposal', confidence: 0.99, pageId: 0, level: 'H1' },
      { id: 'seg_2', type: 'text', box: [22, 10, 38, 25], text: 'This document outlines the strategic initiatives for scaling enterprise infrastructure over the next fiscal year.', confidence: 0.95, pageId: 0 },
      { id: 'seg_3', type: 'text', box: [22, 52, 38, 25], text: 'Key objectives include reducing latency, increasing throughput, and establishing unified analytics.', confidence: 0.92, pageId: 0 },
      { id: 'seg_4', type: 'table', box: [52, 10, 80, 30], text: 'Financial Projections FY24 table region.', confidence: 0.88, pageId: 0 },
      { id: 'seg_5', type: 'image', box: [85, 10, 40, 10], text: 'Architecture diagram visualization flow.', confidence: 0.76, pageId: 0 }
    ];

    setDocumentImage(initImage);
    setSegments(initialMockSegments);
    setHistory([initialMockSegments]);
    setHistoryPointer(0);
  }, [project]);

  useEffect(() => {
    loadBackendConfig();
    loadAnalyzedJobs();
  }, []);

  useEffect(() => {
    if (!analysisJob?.job_id || analysisJob.status === 'complete') {
      if (analysisJob?.status === 'complete') setIsAnalyzing(false);
      return;
    }

    setIsAnalyzing(true);
    const timer = window.setInterval(async () => {
      try {
        const payload = await fetchJson<BackendJob>(`/api/jobs/${analysisJob.job_id}/result`);
        applyJobPayload(payload, false);
        if (payload.status === 'complete') {
          setIsAnalyzing(false);
          setStatusMessage('');
          loadAnalyzedJobs();
          window.clearInterval(timer);
        } else {
          setStatusMessage(`Backend processing ${payload.completed_pages || 0}/${payload.page_count || 0} pages...`);
        }
      } catch (error) {
        setIsAnalyzing(false);
        setErrorMessage(error instanceof Error ? error.message : String(error));
        window.clearInterval(timer);
      }
    }, 1200);

    return () => window.clearInterval(timer);
  }, [analysisJob?.job_id, analysisJob?.status]);

  async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.error) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    return payload as T;
  }

  async function loadBackendConfig() {
    try {
      const payload = await fetchJson<{ config: BackendConfig; prompt_templates?: PromptTemplateOption[] }>('/api/config');
      const cfg = payload.config || {};
      setBaseUrl(cfg.base_url || '');
      setSelectedModel(cfg.model || '');
      setTimeoutValue(cfg.timeout || '180');
      setRenderDpi(cfg.render_dpi || '180');
      setMaxPages(cfg.max_pages || '50');
      setQwenPreset(cfg.qwen_preset || 'default');
      setQwenWidth(cfg.qwen_width || '1536');
      setQwenHeight(cfg.qwen_height || '2176');
      setPromptTemplateId(cfg.prompt_template_id || 'default_template_1');
      if (payload.prompt_templates?.length) setPromptTemplates(payload.prompt_templates);
    } catch (error) {
      setErrorMessage(`Backend config unavailable: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function loadAnalyzedJobs() {
    try {
      const payload = await fetchJson<{ jobs: BackendJobSummary[] }>('/api/jobs');
      setJobs(payload.jobs || []);
    } catch (error) {
      setErrorMessage(`History unavailable: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  function mapBackendJobToSegments(job: BackendJob): AnnotationSegment[] {
    const mapped: AnnotationSegment[] = [];
    (job.pages || []).forEach((page) => {
      (page.blocks || []).forEach((block) => {
        const [x1, y1, x2, y2] = block.bbox || [0, 0, page.width, page.height];
        mapped.push({
          id: block.id,
          type: block.block_type,
          box: [
            clampPercent((y1 / Math.max(page.height, 1)) * 100),
            clampPercent((x1 / Math.max(page.width, 1)) * 100),
            clampPercent(((x2 - x1) / Math.max(page.width, 1)) * 100),
            clampPercent(((y2 - y1) / Math.max(page.height, 1)) * 100)
          ],
          text: block.text || `[${block.bbox?.join(', ') || 'bbox'}]`,
          confidence: 1,
          pageId: page.page_id,
          level: block.level || null,
          weakHeading: Boolean(block.weak_heading),
          bbox: block.bbox
        });
      });
    });
    return mapped;
  }

  function applyJobPayload(payload: BackendJob, record = true) {
    setAnalysisJob(payload);
    setApiSource('backend');
    const nextSegments = mapBackendJobToSegments(payload);
    setSegments(nextSegments);
    if (record) recordHistory(nextSegments);
    if (payload.pages?.length && currentPageIndex >= payload.pages.length) setCurrentPageIndex(0);
    if (payload.status === 'complete') onUpdateProjectProgress(project.id, 100);
  }

  const getColorSchema = (type: BackendBlockType | string) => {
    switch (type) {
      case 'doc_title': return { border: '#3B82F6', bg: 'rgba(59, 130, 246, 0.1)', text: '#3B82F6' };
      case 'paragraph_title': return { border: '#8B5CF6', bg: 'rgba(139, 92, 246, 0.1)', text: '#8B5CF6' };
      case 'text': return { border: '#A78BFA', bg: 'rgba(167, 139, 250, 0.08)', text: '#A78BFA' };
      case 'table': return { border: '#10B981', bg: 'rgba(16, 185, 129, 0.1)', text: '#10B981' };
      case 'figure_title': return { border: '#F59E0B', bg: 'rgba(245, 158, 11, 0.1)', text: '#F59E0B' };
      case 'image': return { border: '#EC4899', bg: 'rgba(236, 72, 153, 0.1)', text: '#EC4899' };
      case 'vision_footnote': return { border: '#14B8A6', bg: 'rgba(20, 184, 166, 0.1)', text: '#14B8A6' };
      default: return { border: '#747878', bg: 'rgba(116, 120, 120, 0.1)', text: '#747878' };
    }
  };

  const currentPageSegments = useMemo(() => {
    const pageId = currentPage?.page_id ?? 0;
    return segments.filter((seg) => {
      if (seg.pageId !== pageId) return false;
      return targetElements[seg.type];
    });
  }, [segments, currentPage?.page_id, targetElements]);

  const visibleSegments = useMemo(() => {
    return segments.filter((seg) => targetElements[seg.type]);
  }, [segments, targetElements]);

  const recordHistory = (newSegments: AnnotationSegment[]) => {
    const nextPointer = historyPointer + 1;
    const historyFork = history.slice(0, nextPointer);
    const updatedHistory = [...historyFork, newSegments];
    setHistory(updatedHistory);
    setHistoryPointer(nextPointer);
  };

  const handleUndo = () => {
    if (historyPointer > 0) {
      const prevPointer = historyPointer - 1;
      setSegments(history[prevPointer]);
      setHistoryPointer(prevPointer);
    }
  };

  const handleRedo = () => {
    if (historyPointer < history.length - 1) {
      const nextPointer = historyPointer + 1;
      setSegments(history[nextPointer]);
      setHistoryPointer(nextPointer);
    }
  };

  const handleAddSegment = (newSeg: AnnotationSegment) => {
    const updated = [...segments, newSeg];
    setSegments(updated);
    recordHistory(updated);
    onIncreaseAnnotationsCount(1);
    const score = Math.min(Math.round((updated.length / 10) * 100), 100);
    onUpdateProjectProgress(project.id, score);
  };

  const handleDeleteSegment = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const updated = segments.filter(s => s.id !== id);
    setSegments(updated);
    recordHistory(updated);
  };

  const handleClearAll = () => {
    setSegments([]);
    recordHistory([]);
  };

  const handleZoomIn = () => setScale(prev => Math.min(prev + 0.1, 1.5));
  const handleZoomOut = () => setScale(prev => Math.max(prev - 0.1, 0.5));
  const handleResetZoom = () => setScale(0.9);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setErrorMessage('Backend analyzer currently accepts PDF files only.');
      return;
    }
    setSelectedFile(file);
    setAnalysisJob(null);
    setCurrentPageIndex(0);
    setSegments([]);
    setSelectedSegmentId(null);
    recordHistory([]);
    setErrorMessage('');
  };

  const triggerReplaceDocument = () => {
    fileInputRef.current?.click();
  };

  const handleStartAnalysis = async () => {
    if (isAnalyzing) return;
    if (!selectedFile) {
      setErrorMessage('Select a PDF document before starting backend analysis.');
      return;
    }

    setIsAnalyzing(true);
    setSegments([]);
    setAnalysisJob(null);
    setCurrentPageIndex(0);
    setStatusMessage('Uploading PDF to backend layout analyzer...');
    setErrorMessage('');
    setApiSource('default');

    const form = new FormData();
    form.append('file', selectedFile);
    form.append('dpi', renderDpi || '180');
    form.append('max_pages', maxPages || '50');
    form.append('base_url', baseUrl.trim());
    form.append('model', selectedModel.trim());
    form.append('api_key', apiKey.trim());
    form.append('timeout', timeout || '180');
    form.append('qwen_preset', qwenPreset || 'default');
    form.append('qwen_width', qwenWidth || '1536');
    form.append('qwen_height', qwenHeight || '2176');
    form.append('prompt_template_id', promptTemplateId || 'default_template_1');

    try {
      const payload = await fetchJson<BackendJob>('/api/analyze', { method: 'POST', body: form });
      applyJobPayload(payload);
      setStatusMessage(`Backend job created. Processing ${payload.completed_pages || 0}/${payload.page_count || 0} pages...`);
      onIncreaseAnnotationsCount(payload.result?.blocks?.length || 0);
      loadAnalyzedJobs();
    } catch (error) {
      setIsAnalyzing(false);
      setStatusMessage('');
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const loadJob = async (jobId: string) => {
    setErrorMessage('');
    try {
      const payload = await fetchJson<BackendJob>(`/api/jobs/${jobId}/result`);
      applyJobPayload(payload);
      setCurrentPageIndex(0);
      setIsAnalyzing(payload.status !== 'complete');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  useEffect(() => {
    if (project.backendJobId) loadJob(project.backendJobId);
  }, [project.backendJobId]);

  const deleteJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('Delete this backend analysis history record?')) return;
    try {
      await fetchJson<{ ok: boolean }>(`/api/jobs/${jobId}`, { method: 'DELETE' });
      if (analysisJob?.job_id === jobId) {
        setAnalysisJob(null);
        setSegments([]);
        setCurrentPageIndex(0);
      }
      loadAnalyzedJobs();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isAnalyzing || !canvasContainerRef.current) return;
    const rect = canvasContainerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setIsDrawing(true);
    setStartPos({ x, y });
    setCurrentDragPos({ x, y });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDrawing || !canvasContainerRef.current) return;
    const rect = canvasContainerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
    setCurrentDragPos({ x, y });
  };

  const handleMouseUp = () => {
    if (!isDrawing || !canvasContainerRef.current) return;
    setIsDrawing(false);
    const rect = canvasContainerRef.current.getBoundingClientRect();
    const wPx = Math.abs(currentDragPos.x - startPos.x);
    const hPx = Math.abs(currentDragPos.y - startPos.y);
    if (wPx < 15 || hPx < 15) return;

    const leftPx = Math.min(startPos.x, currentDragPos.x);
    const topPx = Math.min(startPos.y, currentDragPos.y);
    setDrawnBoxPercent([
      Math.round((topPx / rect.height) * 100),
      Math.round((leftPx / rect.width) * 100),
      Math.round((wPx / rect.width) * 100),
      Math.round((hPx / rect.height) * 100)
    ]);
    setNewBoxText('');
    setNewBoxModalOpen(true);
  };

  const handleCreateDrawnBox = () => {
    if (!drawnBoxPercent) return;
    const newSegment: AnnotationSegment = {
      id: `seg_custom_${Date.now()}`,
      type: newBoxType,
      box: drawnBoxPercent,
      text: newBoxText.trim() || `User annotated ${BLOCK_TYPE_LABELS[newBoxType]} zone`,
      confidence: 1,
      pageId: currentPage?.page_id ?? 0
    };
    handleAddSegment(newSegment);
    setNewBoxModalOpen(false);
    setDrawnBoxPercent(null);
  };

  const getJsonRepresentation = () => {
    return JSON.stringify(analysisJob || { segments }, null, 2);
  };

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(getJsonRepresentation());
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `${(analysisJob?.filename || project.name).replace(/\s+/g, '_')}_annotation_map.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const canvasImage = currentPage?.image_url || documentImage;
  const canvasWidth = 680;
  const canvasHeight = currentPage ? Math.round(canvasWidth * (currentPage.height / Math.max(currentPage.width, 1))) : 880;

  return (
    <div id="layout-workspace-container" className="flex flex-1 flex-col md:flex-row overflow-hidden relative font-sans select-none bg-[#0c0c0c] text-[#e5e5e5]">
      <header className="absolute top-0 left-0 w-full z-40 flex justify-between items-center px-10 h-16 bg-[#0c0c0c]/90 backdrop-blur-md border-b border-white/10">
        <div className="flex items-center gap-4">
          <button
            onClick={onGoBack}
            className="p-2 text-white/60 hover:text-white hover:bg-white/5 rounded-none border border-transparent hover:border-white/10 transition-colors flex items-center justify-center cursor-pointer"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex flex-col">
            <h1 className="font-serif italic text-base text-white flex items-center gap-2 tracking-tight">
              {project.name}
              <span className="px-2 py-0.5 border border-white/10 rounded-none text-[9px] font-mono tracking-wider text-white/70 bg-white/5">
                PDF
              </span>
            </h1>
            <span className="text-[10px] font-mono uppercase tracking-wider text-white/40 flex items-center gap-1 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full ${isAnalyzing ? 'bg-amber-400 animate-pulse' : 'bg-emerald-500'}`} />
              {analysisJob ? `${analysisJob.status} · ${completedPages}/${displayedPageCount} pages` : 'Backend-ready annotation workspace'}
            </span>
          </div>
        </div>

        {apiSource === 'backend' && (
          <div className="hidden lg:flex items-center gap-2 text-[10px] uppercase tracking-wider px-3.5 py-1 bg-white/5 border border-white/10 rounded-none text-white/80 font-mono">
            <CloudLightning className="w-3.5 h-3.5 text-white/70" />
            <span>Python backend · {analysisJob?.config?.model || selectedModel || 'model pending'} · {activeTemplateName}</span>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={handleExportJson}
            className="p-2 text-white/60 hover:text-white hover:bg-white/5 rounded-none border border-transparent hover:border-white/10 transition-colors flex items-center justify-center cursor-pointer"
            title="Download JSON Representation"
          >
            <Download className="w-5 h-5" />
          </button>
          <div className="w-px h-6 bg-white/10 mx-1" />
          <button
            onClick={loadBackendConfig}
            className="px-4 py-2 text-[10px] uppercase tracking-[0.2em] font-bold border border-white/10 rounded-none bg-transparent text-white/80 hover:bg-white/10 hover:text-white transition-colors"
          >
            Sync Config
          </button>
          <button
            onClick={handleExportJson}
            className="px-4 py-2 text-[10px] uppercase tracking-[0.2em] font-bold rounded-none bg-white text-black hover:bg-white/90 transition-all flex items-center gap-2"
          >
            <span>Export JSON</span>
          </button>
        </div>
      </header>

      <div className="flex-1 flex pt-16 h-full overflow-hidden w-full bg-[#0c0c0c]">
        <aside className="w-[340px] h-full flex flex-col border-r border-white/10 bg-[#0c0c0c] z-20 flex-shrink-0 text-[#e5e5e5]">
          <div className="p-6 flex flex-col h-full overflow-y-auto custom-scrollbar">
            <h2 className="font-serif italic text-xl text-white mb-6">Analysis Setup</h2>

            <div
              onClick={triggerReplaceDocument}
              className="mb-5 border border-dashed border-white/20 hover:border-white/40 bg-white/[0.02] hover:bg-white/[0.05] rounded-none p-5 flex flex-col items-center justify-center text-center transition-all cursor-pointer group select-none"
            >
              <Upload className="w-6 h-6 text-white/40 group-hover:text-white mb-2 transition-colors" />
              <p className="text-[10px] uppercase tracking-wider font-semibold text-white/60 group-hover:text-white">Replace PDF Document</p>
              <p className="text-[10px] text-white/35 mt-1 max-w-[230px] truncate">{selectedFile ? selectedFile.name : 'Backend accepts .pdf files'}</p>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>

            {errorMessage && (
              <div className="mb-5 p-3 border border-rose-400/20 bg-rose-500/10 text-rose-100 text-[11px] leading-relaxed font-mono">
                {errorMessage}
              </div>
            )}

            <div className="flex flex-col gap-5 flex-1">
              <div className="flex flex-col gap-2">
                <label className="text-[10px] uppercase tracking-wider font-bold text-white/60 flex items-center justify-between">
                  <span>Model Endpoint</span>
                  <Info className="w-3.5 h-3.5 text-white/40 hover:text-white cursor-help" title="These fields map directly to backend LLM_BASE_URL, LLM_MODEL, API key, and timeout." />
                </label>
                <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="Base URL" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                <input value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)} placeholder="Model name" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                <div className="grid grid-cols-2 gap-2">
                  <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" placeholder="API Key optional" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                  <input value={timeout} onChange={(e) => setTimeoutValue(e.target.value)} type="number" min="10" max="900" placeholder="Timeout" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-[10px] uppercase tracking-wider font-bold text-white/60 flex items-center gap-2">
                  <Settings2 className="w-3.5 h-3.5" /> Render Controls
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input value={renderDpi} onChange={(e) => setRenderDpi(e.target.value)} type="number" min="72" max="300" placeholder="Render DPI" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                  <input value={maxPages} onChange={(e) => setMaxPages(e.target.value)} type="number" min="1" max="200" placeholder="Max pages" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                </div>
                <select value={qwenPreset} onChange={(e) => setQwenPreset(e.target.value)} className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium">
                  <option value="speed">Speed · 1216 × 1728</option>
                  <option value="default">Default · 1536 × 2176</option>
                  <option value="high">High · 2048 × 2912</option>
                  <option value="custom">Custom</option>
                </select>
                {qwenPreset === 'custom' && (
                  <div className="grid grid-cols-2 gap-2">
                    <input value={qwenWidth} onChange={(e) => setQwenWidth(e.target.value)} type="number" min="1024" max="4096" step="32" placeholder="Width" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                    <input value={qwenHeight} onChange={(e) => setQwenHeight(e.target.value)} type="number" min="1024" max="6144" step="32" placeholder="Height" className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium" />
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-[10px] uppercase tracking-wider font-bold text-white/60">Prompt Template</label>
                <select value={promptTemplateId} onChange={(e) => setPromptTemplateId(e.target.value)} className="w-full bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium">
                  {promptTemplates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-3">
                <label className="text-[10px] uppercase tracking-wider font-bold text-white/60">Backend Block Types</label>
                <div className="grid grid-cols-1 gap-1.5">
                  {BLOCK_TYPES.map((type) => {
                    const colorSchema = getColorSchema(type);
                    return (
                      <label key={type} className="flex items-center gap-3 p-2 rounded-none hover:bg-white/[0.03] text-white/70 hover:text-white transition-colors cursor-pointer group select-none text-xs font-medium">
                        <input
                          type="checkbox"
                          checked={targetElements[type]}
                          onChange={(e) => setTargetElements({ ...targetElements, [type]: e.target.checked })}
                          className="w-3.5 h-3.5 text-white border-white/20 bg-[#0e0e0e] rounded-none focus:ring-0 accent-white cursor-pointer"
                        />
                        <span className="flex-1 text-white/60 group-hover:text-white font-medium">{BLOCK_TYPE_LABELS[type]}</span>
                        <div className="w-2.5 h-2.5 rounded-none" style={{ backgroundColor: colorSchema.border }} />
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="mt-2 p-4 border border-white/10 rounded-none bg-white/[0.02] opacity-90">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-bold text-white uppercase tracking-wide flex items-center gap-2"><Database className="w-3.5 h-3.5" /> History</h3>
                  <button onClick={loadAnalyzedJobs} className="text-white/45 hover:text-white"><RefreshCw className="w-3.5 h-3.5" /></button>
                </div>
                <div className="max-h-36 overflow-y-auto custom-scrollbar flex flex-col gap-2 pr-1">
                  {jobs.length === 0 ? (
                    <p className="text-[11px] text-white/40 font-serif italic">No backend history yet.</p>
                  ) : jobs.slice(0, 6).map((job) => (
                    <button key={job.job_id} onClick={() => loadJob(job.job_id)} className={`text-left p-2 border rounded-none transition-colors ${analysisJob?.job_id === job.job_id ? 'border-white/30 bg-white/[0.05]' : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.04]'}`}>
                      <div className="flex justify-between items-start gap-2">
                        <span className="text-[11px] text-white/80 font-bold truncate">{job.filename}</span>
                        <span onClick={(e) => deleteJob(job.job_id, e)} className="text-white/35 hover:text-rose-300"><Trash2 className="w-3.5 h-3.5" /></span>
                      </div>
                      <p className="text-[9px] text-white/35 font-mono mt-1">{job.status} · {job.completed_pages}/{job.page_count} pages · {job.block_count} blocks</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-8 pt-4 border-t border-white/10">
              <button
                onClick={handleStartAnalysis}
                disabled={isAnalyzing}
                className={`w-full py-3.5 text-[10px] uppercase tracking-[0.25em] font-bold rounded-none flex items-center justify-center gap-2 select-none shadow-sm transition-all duration-150 h-12 ${
                  isAnalyzing
                    ? 'bg-white/5 text-white/30 cursor-not-allowed border border-white/5'
                    : 'bg-white text-black hover:bg-white/90 active:scale-[0.99] cursor-pointer'
                }`}
              >
                {isAnalyzing ? (
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-transparent rounded-full animate-spin" />
                    <span>Analyzing Layout...</span>
                  </div>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current text-black" />
                    <span>Start Analysis</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </aside>

        <section className="flex-1 relative bg-[#131313] flex items-center justify-center overflow-hidden h-full">
          {isAnalyzing && (
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-30 flex flex-col items-center justify-center text-center p-6 select-none">
              <div className="bg-[#0e0e0e] p-6 rounded-none border border-white/10 shadow-2xl flex flex-col items-center max-w-sm justify-center">
                <span className="w-10 h-10 border-4 border-white border-t-transparent rounded-full animate-spin mb-4" />
                <h4 className="font-serif italic text-sm text-white">Backend Layout Engine Processing</h4>
                <p className="text-xs text-white/50 mt-2 animate-pulse leading-relaxed">{statusMessage}</p>
              </div>
            </div>
          )}

          {analysisJob?.pages?.length ? (
            <div className="absolute top-4 left-4 z-20 flex items-center gap-2 bg-[#0c0c0c]/90 border border-white/10 px-3 py-2 text-[10px] font-mono text-white/70">
              <FileText className="w-3.5 h-3.5" />
              <select value={currentPageIndex} onChange={(e) => setCurrentPageIndex(Number(e.target.value))} className="bg-transparent text-white focus:outline-none">
                {analysisJob.pages.map((page, idx) => (
                  <option key={page.page_id} value={idx}>Page {page.page_id + 1} · {page.status || 'pending'}</option>
                ))}
              </select>
            </div>
          ) : selectedFile ? (
            <div className="absolute top-4 left-4 z-20 bg-[#0c0c0c]/90 border border-white/10 px-3 py-2 text-[10px] font-mono text-white/60">
              {selectedFile.name} ready for backend analysis
            </div>
          ) : null}

          <div className="overflow-auto max-w-full max-h-full p-12 flex items-center justify-center custom-scrollbar w-full h-full">
            <motion.div
              className="relative bg-[#fafafc] shadow-2xl rounded-none transition-all overflow-hidden cursor-crosshair border border-white/10"
              style={{
                width: `${canvasWidth}px`,
                height: `${canvasHeight}px`,
                transform: `scale(${scale})`,
                transformOrigin: 'center center',
                backgroundImage: canvasImage ? `url(${canvasImage})` : undefined,
                backgroundSize: '100% 100%',
                backgroundPosition: 'center',
              }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              ref={canvasContainerRef}
              id="document-canvas-board"
            >
              {!canvasImage && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8 bg-[#f4f4f5] text-black/45">
                  <FileText className="w-10 h-10 mb-3" />
                  <p className="font-serif italic text-lg text-black/60">Select a PDF and start analysis</p>
                </div>
              )}

              {currentPageSegments.map((seg) => {
                const colors = getColorSchema(seg.type);
                const isSelected = selectedSegmentId === seg.id;
                return (
                  <div
                    key={seg.id}
                    onMouseEnter={() => setSelectedSegmentId(seg.id)}
                    onMouseLeave={() => setSelectedSegmentId(null)}
                    className="absolute border-2 transition-all cursor-pointer bbox select-none group"
                    style={{
                      left: `${seg.box[1]}%`,
                      top: `${seg.box[0]}%`,
                      width: `${seg.box[2]}%`,
                      height: `${seg.box[3]}%`,
                      borderColor: colors.border,
                      backgroundColor: isSelected ? 'rgba(255, 255, 255, 0.12)' : colors.bg,
                      boxShadow: isSelected ? `0 0 12px ${colors.border}` : 'none',
                      zIndex: isSelected ? 15 : 10
                    }}
                  >
                    <div className="absolute text-[9px] px-2 py-0.5 rounded-none text-white font-mono uppercase tracking-wider whitespace-nowrap -top-5 -left-[2px]" style={{ backgroundColor: colors.border }}>
                      {seg.level ? `${seg.level} · ` : ''}{BLOCK_TYPE_LABELS[seg.type]}
                    </div>
                    <button onClick={(e) => handleDeleteSegment(seg.id, e)} className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 hover:bg-rose-600 hover:text-white p-1 rounded-none transition-opacity bg-black/80 border border-white/10 text-white/80 shadow z-20">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })}

              {isDrawing && canvasContainerRef.current && (
                <div className="absolute border-2 border-dashed border-white bg-white/10 pointer-events-none z-30" style={{ left: `${Math.min(startPos.x, currentDragPos.x)}px`, top: `${Math.min(startPos.y, currentDragPos.y)}px`, width: `${Math.abs(currentDragPos.x - startPos.x)}px`, height: `${Math.abs(currentDragPos.y - startPos.y)}px` }} />
              )}
            </motion.div>
          </div>

          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 bg-[#0c0c0c]/90 border border-white/10 backdrop-blur-md px-5 py-2.5 flex items-center gap-3 shadow-2xl z-25 select-none rounded-none text-white shadow-black/60">
            <button onClick={handleUndo} disabled={historyPointer <= 0} className={`p-2 rounded-none transition-colors flex items-center justify-center ${historyPointer <= 0 ? 'text-white/20' : 'text-white hover:bg-white/5'}`} title="Undo Action"><Undo2 className="w-4 h-4" /></button>
            <button onClick={handleRedo} disabled={historyPointer >= history.length - 1} className={`p-2 rounded-none transition-colors flex items-center justify-center ${historyPointer >= history.length - 1 ? 'text-white/20' : 'text-white hover:bg-white/5'}`} title="Redo Action"><Redo2 className="w-4 h-4" /></button>
            <div className="w-px h-5 bg-white/10 mx-1" />
            <button onClick={handleZoomOut} className="p-2 text-white/70 hover:text-white hover:bg-white/5 rounded-none transition-colors flex items-center justify-center" title="Zoom Out"><ZoomOut className="w-4 h-4" /></button>
            <span className="text-[10px] font-mono font-bold text-white min-w-[40px] text-center">{Math.round(scale * 100)}%</span>
            <button onClick={handleZoomIn} className="p-2 text-white/70 hover:text-white hover:bg-white/5 rounded-none transition-colors flex items-center justify-center" title="Zoom In"><ZoomIn className="w-4 h-4" /></button>
            <div className="w-px h-5 bg-white/10 mx-1" />
            <button onClick={handleResetZoom} className="p-2 text-white/70 hover:text-white hover:bg-white/5 rounded-none transition-colors flex items-center justify-center" title="Reset Zoom to Fit"><Maximize2 className="w-4 h-4" /></button>
          </div>
        </section>

        <aside className="w-[380px] h-full flex flex-col border-l border-white/10 bg-[#0c0c0c] z-20 flex-shrink-0 text-[#e5e5e5]">
          <div className="flex border-b border-white/10 pt-4 px-4 bg-[#0c0c0c]">
            <button onClick={() => setActiveTab('list')} className={`flex-1 pb-3 text-[10px] uppercase tracking-wider font-bold flex items-center justify-center gap-2 border-b-2 transition-all cursor-pointer ${activeTab === 'list' ? 'text-white border-white' : 'text-white/40 hover:text-white border-transparent'}`}>
              <List className="w-4 h-4" /><span>Blocks Identified</span>
            </button>
            <button onClick={() => setActiveTab('json')} className={`flex-1 pb-3 text-[10px] uppercase tracking-wider font-bold flex items-center justify-center gap-2 border-b-2 transition-all cursor-pointer ${activeTab === 'json' ? 'text-white border-white' : 'text-white/40 hover:text-white border-transparent'}`}>
              <Code2 className="w-4 h-4" /><span>JSON Payload</span>
            </button>
          </div>

          <div className="p-4 border-b border-white/5 bg-white/[0.01] text-xs text-white/45">
            <div className="grid grid-cols-3 gap-2 mb-3">
              <div className="border border-white/10 bg-white/[0.02] p-2"><b className="block text-white text-base font-mono">{displayedPageCount || '-'}</b><span className="text-[9px] uppercase tracking-wider">Pages</span></div>
              <div className="border border-white/10 bg-white/[0.02] p-2"><b className="block text-white text-base font-mono">{visibleSegments.length}</b><span className="text-[9px] uppercase tracking-wider">Blocks</span></div>
              <div className="border border-white/10 bg-white/[0.02] p-2"><b className="block text-white text-base font-mono">{analysisJob?.errors?.length || 0}</b><span className="text-[9px] uppercase tracking-wider">Errors</span></div>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-mono">{currentPageSegments.length} blocks on current page</span>
              <button onClick={handleClearAll} className="hover:underline font-bold text-white/80 cursor-pointer">Clear Local Map</button>
            </div>
          </div>

          <div className="flex-grow overflow-y-auto custom-scrollbar p-4 bg-[#0c0c0c]">
            <AnimatePresence mode="wait">
              {activeTab === 'list' ? (
                <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} className="flex flex-col gap-3">
                  {currentPageSegments.length === 0 ? (
                    <div className="text-center py-16 px-4">
                      <AlertTriangle className="w-8 h-8 mx-auto text-white/35 mb-3" />
                      <p className="text-white/50 text-xs">No backend blocks matching the current filters on this page.</p>
                      <button onClick={handleStartAnalysis} className="mt-4 text-xs font-bold underline text-white/80 hover:text-white">Run backend analysis</button>
                    </div>
                  ) : currentPageSegments.map((seg) => {
                    const colors = getColorSchema(seg.type);
                    const isSelected = selectedSegmentId === seg.id;
                    return (
                      <div key={seg.id} onMouseEnter={() => setSelectedSegmentId(seg.id)} onMouseLeave={() => setSelectedSegmentId(null)} className={`bg-[#0e0e0e] border p-3.5 flex flex-col gap-2.5 transition-all cursor-pointer relative group rounded-none ${isSelected ? 'border-white/40 bg-white/[0.03] shadow-lg shadow-black/30' : 'border-white/5 hover:border-white/10'}`}>
                        <div className="flex justify-between items-center">
                          <div className="flex items-center gap-2 select-none">
                            <div className="w-1.5 h-1.5 rounded-none" style={{ backgroundColor: colors.border }} />
                            <span className="text-[10px] font-mono font-bold text-white uppercase tracking-wider">{seg.level ? `${seg.level} · ` : ''}{BLOCK_TYPE_LABELS[seg.type]}</span>
                          </div>
                          <span className="text-[9px] font-mono bg-white/10 px-1.5 py-0.5 rounded-none text-white/80 border border-white/5 font-bold">p{(seg.pageId || 0) + 1}</span>
                        </div>
                        {seg.type === 'table' ? (
                          <div className="flex items-center gap-2 bg-white/[0.02] p-2 rounded-none text-xs text-white/80 font-medium border border-white/5"><Table className="w-4 h-4 text-white/50" /><span className="truncate font-serif italic text-white/60">{seg.text}</span></div>
                        ) : seg.type === 'image' || seg.type === 'figure_title' ? (
                          <div className="flex items-center gap-2 bg-white/[0.02] p-2 rounded-none text-xs text-white/80 font-medium border border-white/5"><ImageIcon className="w-4 h-4 text-white/50" /><span className="truncate font-serif italic text-white/60">{seg.text}</span></div>
                        ) : (
                          <p className="text-xs text-white/60 leading-relaxed line-clamp-3 font-sans">{seg.text}</p>
                        )}
                        <button onClick={(e) => handleDeleteSegment(seg.id, e)} className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 text-white/40 hover:text-rose-500 font-bold transition-all p-1 rounded-none hover:bg-white/5"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    );
                  })}
                </motion.div>
              ) : (
                <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} className="h-full flex flex-col gap-2 font-mono text-[11px]">
                  <div className="relative">
                    <pre className="bg-[#0e0e0e] text-[#858383] p-4 rounded-none border border-white/10 overflow-x-auto select-text custom-scrollbar leading-relaxed"><code className="text-stone-300">{getJsonRepresentation()}</code></pre>
                    <button onClick={() => { navigator.clipboard.writeText(getJsonRepresentation()); alert('JSON mappings copied to clipboard!'); }} className="absolute top-2 right-2 px-2.5 py-1 text-[9px] uppercase tracking-wider font-bold bg-[#141414] border border-white/10 text-white/80 hover:bg-white hover:text-black rounded-none transition-colors">Copy</button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </aside>
      </div>

      <AnimatePresence>
        {newBoxModalOpen && drawnBoxPercent && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 select-none">
            <div className="bg-[#0e0e0e] rounded-none p-6 max-w-sm w-full border border-white/10 shadow-2xl relative text-white">
              <h3 className="font-serif italic text-base text-white mb-4">Annotate Backend Block</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-[9px] font-mono font-bold uppercase tracking-wider text-white/50 mb-1">Block Classification</label>
                  <select value={newBoxType} onChange={(e) => setNewBoxType(e.target.value as BackendBlockType)} className="w-full px-3 py-1.5 bg-[#0c0c0c] border border-white/10 rounded-none text-xs font-serif italic text-white focus:outline-none focus:border-white/30">
                    {BLOCK_TYPES.map((type) => <option key={type} value={type}>{BLOCK_TYPE_LABELS[type]}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[9px] font-mono font-bold uppercase tracking-wider text-white/50 mb-1">Transcription</label>
                  <input type="text" required placeholder="Transcribe block text or descriptive name..." value={newBoxText} onChange={(e) => setNewBoxText(e.target.value)} className="w-full px-3 py-1.5 bg-[#0c0c0c] border border-white/10 rounded-none text-xs text-white placeholder-white/30 focus:outline-none focus:border-white/30" />
                </div>
                <div className="bg-white/[0.01] p-3 rounded-none border border-white/5 text-[10px] text-white/50 font-mono">
                  <span className="block font-bold text-white/70 mb-0.5 uppercase tracking-wider">Calculated Bounding Box</span>
                  <span>Top: {drawnBoxPercent[0]}%, Left: {drawnBoxPercent[1]}%, Width: {drawnBoxPercent[2]}%, Height: {drawnBoxPercent[3]}%</span>
                </div>
              </div>
              <div className="mt-5 flex justify-end gap-3 pt-3 border-t border-white/10">
                <button onClick={() => { setNewBoxModalOpen(false); setDrawnBoxPercent(null); }} className="px-3.5 py-1.5 text-[10px] uppercase tracking-wider font-bold border border-white/10 hover:bg-white/5 rounded-none text-white/80 cursor-pointer">Cancel</button>
                <button onClick={handleCreateDrawnBox} className="px-4 py-1.5 text-[10px] uppercase tracking-wider font-bold bg-white text-black hover:bg-white/90 rounded-none cursor-pointer">Create Label</button>
              </div>
            </div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Number(value.toFixed(3))));
}
