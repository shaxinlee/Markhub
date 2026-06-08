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
  Settings2,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import { Project, AnnotationSegment, BackendBlockType, BackendBlock, BackendPage, BackendJob, BackendJobSummary, BackendConfig, PromptTemplateOption } from '../types';
import { motion, AnimatePresence } from 'motion/react';

interface WorkspaceProps {
  project: Project;
  onGoBack: () => void;
  onUpdateProjectProgress: (projectId: string, progress: number) => void;
  onIncreaseAnnotationsCount: (increment: number) => void;
}

const BLOCK_TYPES: BackendBlockType[] = [
  'doc_title',
  'paragraph_title',
  'text',
  'table_of_contents',
  'table',
  'formula',
  'chart',
  'image',
  'vision_footnote',
  'header',
  'footer',
  'caption',
  'handwriting',
  'seal'
];

const BLOCK_TYPE_LABELS: Record<BackendBlockType, string> = {
  doc_title: 'Doc Title',
  paragraph_title: 'Paragraph Title',
  text: 'Text',
  table_of_contents: 'Table of Contents',
  table: 'Table',
  formula: 'Formula',
  chart: 'Chart',
  image: 'Image',
  vision_footnote: 'Footnote',
  header: 'Header',
  footer: 'Footer',
  caption: 'Caption',
  handwriting: 'Handwriting',
  seal: 'Seal'
};

const DEFAULT_VISIBLE_TYPES: Record<BackendBlockType, boolean> = {
  doc_title: true,
  paragraph_title: true,
  text: true,
  table_of_contents: true,
  table: true,
  formula: true,
  chart: true,
  image: true,
  vision_footnote: true,
  header: true,
  footer: true,
  caption: true,
  handwriting: true,
  seal: true
};

function normalizeBackendBlockType(type: string): BackendBlockType {
  const aliases: Record<string, BackendBlockType> = {
    list: 'table_of_contents',
    title: 'paragraph_title',
    figure_title: 'caption',
    figure: 'image',
    footnote: 'vision_footnote',
    reference: 'vision_footnote',
    other: 'text',
  };
  const normalized = aliases[type] || type;
  return BLOCK_TYPES.includes(normalized as BackendBlockType) ? (normalized as BackendBlockType) : 'text';
}

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
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [apiSource, setApiSource] = useState<'default' | 'backend'>('default');

  const [analysisJob, setAnalysisJob] = useState<BackendJob | null>(null);
  const [batchJobIds, setBatchJobIds] = useState<string[]>([]);
  const [batchProgress, setBatchProgress] = useState({
    totalFiles: 0,
    completedFiles: 0,
    totalPages: 0,
    completedPages: 0
  });
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
  const availablePageCount = analysisJob?.pages?.length || 0;
  const completedPages = analysisJob?.completed_pages || 0;
  const activeTemplateName = analysisJob?.prompt_template?.name || promptTemplates.find(t => t.id === promptTemplateId)?.name || '默认模板 1';
  const selectedFileSummary = selectedFiles.length === 0
    ? 'Backend accepts .pdf files'
    : selectedFiles.length === 1
      ? selectedFiles[0].name
      : `${selectedFiles.length} PDF files selected`;
  const headerStatus = batchJobIds.length > 1
    ? `${batchProgress.completedFiles}/${batchProgress.totalFiles || batchJobIds.length} files · ${batchProgress.completedPages}/${batchProgress.totalPages} pages`
    : analysisJob
      ? `${analysisJob.status} · ${completedPages}/${displayedPageCount} pages`
      : 'Backend-ready annotation workspace';

  useEffect(() => {
    setDocumentImage(project.images?.[0] || '');
    setSelectedFiles([]);
    setBatchJobIds([]);
    setBatchProgress({ totalFiles: 0, completedFiles: 0, totalPages: 0, completedPages: 0 });
    setSegments([]);
    setHistory([[]]);
    setHistoryPointer(0);
    setAnalysisJob(null);
    setCurrentPageIndex(0);
    setSelectedSegmentId(null);
  }, [project]);

  useEffect(() => {
    loadBackendConfig();
    loadAnalyzedJobs();
  }, []);

  useEffect(() => {
    if (batchJobIds.length > 0) return;
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
  }, [analysisJob?.job_id, analysisJob?.status, batchJobIds.length]);

  useEffect(() => {
    if (batchJobIds.length === 0) return;

    let cancelled = false;

    async function pollBatchJobs() {
      try {
        const payloads = await Promise.all(batchJobIds.map((jobId) => fetchJson<BackendJob>(`/api/jobs/${jobId}/result`)));
        if (cancelled) return;

        const totalPages = payloads.reduce((sum, job) => sum + (job.page_count || 0), 0);
        const completedPageCount = payloads.reduce((sum, job) => sum + (job.completed_pages || 0), 0);
        const completedFileCount = payloads.filter((job) => isBackendJobComplete(job.status)).length;
        const totalFileCount = batchJobIds.length;

        setBatchProgress({
          totalFiles: totalFileCount,
          completedFiles: completedFileCount,
          totalPages,
          completedPages: completedPageCount
        });

        const activePayload = payloads.find((job) => job.job_id === analysisJob?.job_id) || payloads[0];
        if (activePayload) applyJobPayload(activePayload, false, false);

        loadAnalyzedJobs();

        if (completedFileCount >= totalFileCount) {
          setIsAnalyzing(false);
          setBatchJobIds([]);
          setStatusMessage(`Batch complete: ${completedFileCount}/${totalFileCount} files analyzed.`);
          onUpdateProjectProgress(project.id, 100);
        } else {
          setIsAnalyzing(true);
          setStatusMessage(`Batch processing ${completedFileCount}/${totalFileCount} files · ${completedPageCount}/${totalPages} pages...`);
        }
      } catch (error) {
        if (cancelled) return;
        setIsAnalyzing(false);
        setBatchJobIds([]);
        setErrorMessage(error instanceof Error ? error.message : String(error));
      }
    }

    pollBatchJobs();
    const timer = window.setInterval(pollBatchJobs, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [batchJobIds, analysisJob?.job_id, project.id]);

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
          type: normalizeBackendBlockType(block.block_type),
          box: [
            clampPercent((y1 / Math.max(page.height, 1)) * 100),
            clampPercent((x1 / Math.max(page.width, 1)) * 100),
            clampPercent(((x2 - x1) / Math.max(page.width, 1)) * 100),
            clampPercent(((y2 - y1) / Math.max(page.height, 1)) * 100)
          ],
          text: block.text || `[${block.bbox?.join(', ') || 'bbox'}]`,
          chartDescription: block.chart_description || '',
          confidence: 1,
          pageId: page.page_id,
          level: block.level || null,
          bbox: block.bbox
        });
      });
    });
    return mapped;
  }

  function applyJobPayload(payload: BackendJob, record = true, updateProject = true) {
    setAnalysisJob(payload);
    setApiSource('backend');
    const nextSegments = mapBackendJobToSegments(payload);
    setSegments(nextSegments);
    if (record) recordHistory(nextSegments);
    if (payload.pages?.length && currentPageIndex >= payload.pages.length) setCurrentPageIndex(0);
    if (updateProject && isBackendJobComplete(payload.status)) onUpdateProjectProgress(project.id, 100);
  }

  const getColorSchema = (type: BackendBlockType | string) => {
    switch (type) {
      case 'doc_title': return { border: '#3B82F6', bg: 'rgba(59, 130, 246, 0.1)', text: '#3B82F6' };
      case 'paragraph_title': return { border: '#8B5CF6', bg: 'rgba(139, 92, 246, 0.1)', text: '#8B5CF6' };
      case 'text': return { border: '#A78BFA', bg: 'rgba(167, 139, 250, 0.08)', text: '#A78BFA' };
      case 'table_of_contents': return { border: '#06B6D4', bg: 'rgba(6, 182, 212, 0.09)', text: '#06B6D4' };
      case 'table': return { border: '#10B981', bg: 'rgba(16, 185, 129, 0.1)', text: '#10B981' };
      case 'formula': return { border: '#F43F5E', bg: 'rgba(244, 63, 94, 0.1)', text: '#F43F5E' };
      case 'chart': return { border: '#22C55E', bg: 'rgba(34, 197, 94, 0.1)', text: '#22C55E' };
      case 'image': return { border: '#EC4899', bg: 'rgba(236, 72, 153, 0.1)', text: '#EC4899' };
      case 'vision_footnote': return { border: '#14B8A6', bg: 'rgba(20, 184, 166, 0.1)', text: '#14B8A6' };
      case 'header': return { border: '#64748B', bg: 'rgba(100, 116, 139, 0.1)', text: '#64748B' };
      case 'footer': return { border: '#78716C', bg: 'rgba(120, 113, 108, 0.1)', text: '#78716C' };
      case 'caption': return { border: '#D946EF', bg: 'rgba(217, 70, 239, 0.1)', text: '#D946EF' };
      case 'handwriting': return { border: '#F97316', bg: 'rgba(249, 115, 22, 0.1)', text: '#F97316' };
      case 'seal': return { border: '#EF4444', bg: 'rgba(239, 68, 68, 0.1)', text: '#EF4444' };
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

  const goToPage = (nextIndex: number) => {
    if (!analysisJob?.pages?.length) return;
    const clampedIndex = Math.max(0, Math.min(nextIndex, analysisJob.pages.length - 1));
    setCurrentPageIndex(clampedIndex);
    setSelectedSegmentId(null);
  };

  const goToPreviousPage = () => goToPage(currentPageIndex - 1);
  const goToNextPage = () => goToPage(currentPageIndex + 1);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []) as File[];
    if (files.length === 0) return;
    const nonPdf = files.find((file) => !file.name.toLowerCase().endsWith('.pdf'));
    if (nonPdf) {
      setErrorMessage(`Backend analyzer accepts PDF files only: ${nonPdf.name}`);
      e.target.value = '';
      return;
    }
    setSelectedFiles(files);
    setBatchJobIds([]);
    setBatchProgress({ totalFiles: files.length, completedFiles: 0, totalPages: 0, completedPages: 0 });
    setAnalysisJob(null);
    setCurrentPageIndex(0);
    setSegments([]);
    setSelectedSegmentId(null);
    recordHistory([]);
    setErrorMessage('');
    e.target.value = '';
  };

  const triggerReplaceDocument = () => {
    fileInputRef.current?.click();
  };

  const handleStartAnalysis = async () => {
    if (isAnalyzing) return;
    if (selectedFiles.length === 0) {
      setErrorMessage('Select one or more PDF documents before starting backend analysis.');
      return;
    }

    setIsAnalyzing(true);
    setBatchJobIds([]);
    setSegments([]);
    setAnalysisJob(null);
    setCurrentPageIndex(0);
    setStatusMessage(`Uploading ${selectedFiles.length} PDF file${selectedFiles.length > 1 ? 's' : ''} to backend layout analyzer...`);
    setErrorMessage('');
    setApiSource('default');

    try {
      const createdJobs: BackendJob[] = [];
      for (let index = 0; index < selectedFiles.length; index += 1) {
        const file = selectedFiles[index];
        const form = createAnalysisForm(file);
        setStatusMessage(`Creating backend jobs ${index + 1}/${selectedFiles.length}: ${file.name}`);
        const payload = await fetchJson<BackendJob>('/api/analyze', { method: 'POST', body: form });
        createdJobs.push(payload);
        if (index === 0) applyJobPayload(payload, true, selectedFiles.length === 1);
      }

      const jobIds = createdJobs.map((job) => job.job_id);
      const totalPages = createdJobs.reduce((sum, job) => sum + (job.page_count || 0), 0);
      setBatchProgress({ totalFiles: jobIds.length, completedFiles: 0, totalPages, completedPages: 0 });
      setBatchJobIds(jobIds);
      setStatusMessage(
        jobIds.length > 1
          ? `Batch created ${jobIds.length} jobs · 0/${totalPages} pages processed...`
          : `Backend job created. Processing ${createdJobs[0]?.completed_pages || 0}/${createdJobs[0]?.page_count || 0} pages...`
      );
      onIncreaseAnnotationsCount(createdJobs.reduce((sum, job) => sum + (job.result?.blocks?.length || 0), 0));
      loadAnalyzedJobs();
    } catch (error) {
      setIsAnalyzing(false);
      setBatchJobIds([]);
      setStatusMessage('');
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const createAnalysisForm = (file: File) => {
    const form = new FormData();
    form.append('file', file);
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
    return form;
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
      chartDescription: '',
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
    <div id="layout-workspace-container" className="flex flex-1 flex-col overflow-hidden relative font-sans select-none bg-surface-container-low text-on-surface">
      <header className="absolute top-0 left-0 w-full z-40 flex justify-between items-center px-6 md:px-10 h-16 bg-surface/90 backdrop-blur-xl border-b border-outline-variant/40">
        <div className="flex items-center gap-4">
          <button
            onClick={onGoBack}
            className="flex items-center justify-center rounded-full border border-transparent p-2 text-on-surface-variant transition-colors hover:border-outline-variant/50 hover:bg-surface-container hover:text-primary"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex flex-col">
            <h1 className="flex items-center gap-2 text-label-md font-semibold tracking-tight text-primary">
              {project.name}
              <span className="rounded-full border border-outline-variant/50 bg-surface-container px-2 py-0.5 text-[9px] font-mono tracking-wider text-on-surface-variant">
                PDF
              </span>
            </h1>
            <span className="mt-0.5 flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-on-surface-variant">
              <span className={`w-1.5 h-1.5 rounded-full ${isAnalyzing ? 'bg-amber-400 animate-pulse' : 'bg-emerald-500'}`} />
              {headerStatus}
            </span>
          </div>
        </div>

        {apiSource === 'backend' && (
          <div className="hidden items-center gap-2 rounded-full border border-outline-variant/50 bg-surface-container px-3.5 py-1 text-[10px] font-mono uppercase tracking-wider text-on-surface-variant lg:flex">
            <CloudLightning className="w-3.5 h-3.5 text-primary" />
            <span>Python backend · {analysisJob?.config?.model || selectedModel || 'model pending'} · {activeTemplateName}</span>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={handleExportJson}
            className="flex items-center justify-center rounded-full border border-transparent p-2 text-on-surface-variant transition-colors hover:border-outline-variant/50 hover:bg-surface-container hover:text-primary"
            title="Download JSON Representation"
          >
            <Download className="w-5 h-5" />
          </button>
          <div className="w-px h-6 bg-outline-variant/60 mx-1" />
          <button
            onClick={loadBackendConfig}
            className="rounded-[0.75rem] border border-outline-variant/50 px-4 py-2 text-[10px] font-bold uppercase tracking-[0.2em] text-primary transition-colors hover:bg-surface-container"
          >
            Sync Config
          </button>
          <button
            onClick={handleExportJson}
            className="flex items-center gap-2 rounded-[0.75rem] bg-primary px-4 py-2 text-[10px] font-bold uppercase tracking-[0.2em] text-on-primary transition-all hover:bg-primary/90"
          >
            <span>Export JSON</span>
          </button>
        </div>
      </header>

      <div className="flex-1 flex pt-16 h-full overflow-hidden w-full bg-surface-container-low">
        <aside className="w-[340px] h-full flex flex-col border-r border-outline-variant/40 bg-surface-container-lowest z-20 flex-shrink-0 text-on-surface">
          <div className="p-6 flex flex-col h-full overflow-y-auto custom-scrollbar">
            <h2 className="mb-6 text-headline-sm font-semibold text-primary">Analysis Setup</h2>

            <div
              onClick={triggerReplaceDocument}
              className="mb-5 flex cursor-pointer select-none flex-col items-center justify-center rounded-[0.75rem] border border-dashed border-outline-variant/60 bg-surface-container p-5 text-center transition-all hover:border-primary/50 hover:bg-surface-container-high"
            >
              <Upload className="mb-2 h-6 w-6 text-on-surface-variant transition-colors group-hover:text-primary" />
              <p className="text-[10px] font-semibold uppercase tracking-wider text-on-surface-variant group-hover:text-primary">Select PDF Documents</p>
              <p className="mt-1 max-w-[230px] truncate text-[10px] text-on-surface-variant">{selectedFileSummary}</p>
              {selectedFiles.length > 1 && (
                <p className="mt-1 text-[9px] font-mono uppercase tracking-wider text-on-surface-variant">
                  Batch ready · {selectedFiles.length} files
                </p>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                multiple
                onChange={handleFileChange}
                className="hidden"
              />
            </div>

            {errorMessage && (
              <div className="mb-5 rounded-[0.75rem] border border-error/20 bg-error/10 p-3 text-[11px] font-mono leading-relaxed text-error">
                {errorMessage}
              </div>
            )}

            <div className="flex flex-col gap-5 flex-1">
              <div className="flex flex-col gap-2">
                <label className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">
                  <span>Model Endpoint</span>
                  <Info className="h-3.5 w-3.5 cursor-help text-on-surface-variant hover:text-primary" title="These fields map directly to backend LLM_BASE_URL, LLM_MODEL, API key, and timeout." />
                </label>
                <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="Base URL" className="w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-xs font-medium text-on-surface outline-none focus:border-primary" />
                <input value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)} placeholder="Model name" className="w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-xs font-medium text-on-surface outline-none focus:border-primary" />
                <div className="grid grid-cols-2 gap-2">
                  <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" placeholder="API Key optional" className="w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-xs font-medium text-on-surface outline-none focus:border-primary" />
                  <input value={timeout} onChange={(e) => setTimeoutValue(e.target.value)} type="number" min="10" max="900" placeholder="Timeout" className="w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-xs font-medium text-on-surface outline-none focus:border-primary" />
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-[10px] uppercase tracking-wider font-bold text-on-surface-variant flex items-center gap-2">
                  <Settings2 className="w-3.5 h-3.5" /> Render Controls
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input value={renderDpi} onChange={(e) => setRenderDpi(e.target.value)} type="number" min="72" max="300" placeholder="Render DPI" className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-[0.75rem] px-3 py-2.5 text-xs text-primary focus:outline-none focus:border-outline-variant/70 font-medium" />
                  <input value={maxPages} onChange={(e) => setMaxPages(e.target.value)} type="number" min="1" max="200" placeholder="Max pages" className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-[0.75rem] px-3 py-2.5 text-xs text-primary focus:outline-none focus:border-outline-variant/70 font-medium" />
                </div>
                <select value={qwenPreset} onChange={(e) => setQwenPreset(e.target.value)} className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-[0.75rem] px-3 py-2.5 text-xs text-primary focus:outline-none focus:border-outline-variant/70 font-medium">
                  <option value="speed">Speed · 1216 × 1728</option>
                  <option value="default">Default · 1536 × 2176</option>
                  <option value="high">High · 2048 × 2912</option>
                  <option value="custom">Custom</option>
                </select>
                {qwenPreset === 'custom' && (
                  <div className="grid grid-cols-2 gap-2">
                    <input value={qwenWidth} onChange={(e) => setQwenWidth(e.target.value)} type="number" min="1024" max="4096" step="32" placeholder="Width" className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-[0.75rem] px-3 py-2.5 text-xs text-primary focus:outline-none focus:border-outline-variant/70 font-medium" />
                    <input value={qwenHeight} onChange={(e) => setQwenHeight(e.target.value)} type="number" min="1024" max="6144" step="32" placeholder="Height" className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-[0.75rem] px-3 py-2.5 text-xs text-primary focus:outline-none focus:border-outline-variant/70 font-medium" />
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-[10px] uppercase tracking-wider font-bold text-on-surface-variant">Prompt Template</label>
                <select value={promptTemplateId} onChange={(e) => setPromptTemplateId(e.target.value)} className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-[0.75rem] px-3 py-2.5 text-xs text-primary focus:outline-none focus:border-outline-variant/70 font-medium">
                  {promptTemplates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-3">
                <label className="text-[10px] uppercase tracking-wider font-bold text-on-surface-variant">Backend Block Types</label>
                <div className="grid grid-cols-1 gap-1.5">
                  {BLOCK_TYPES.map((type) => {
                    const colorSchema = getColorSchema(type);
                    return (
                      <label key={type} className="flex items-center gap-3 p-2 rounded-[0.75rem] hover:bg-surface-container text-on-surface-variant hover:text-primary transition-colors cursor-pointer group select-none text-xs font-medium">
                        <input
                          type="checkbox"
                          checked={targetElements[type]}
                          onChange={(e) => setTargetElements({ ...targetElements, [type]: e.target.checked })}
                          className="w-3.5 h-3.5 text-primary border-outline-variant/60 bg-surface-container-lowest rounded-[0.75rem] focus:ring-0 accent-white cursor-pointer"
                        />
                        <span className="flex-1 text-on-surface-variant group-hover:text-primary font-medium">{BLOCK_TYPE_LABELS[type]}</span>
                        <div className="w-2.5 h-2.5 rounded-[0.75rem]" style={{ backgroundColor: colorSchema.border }} />
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="mt-2 p-4 border border-outline-variant/40 rounded-[0.75rem] bg-surface-container opacity-90">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-bold text-primary uppercase tracking-wide flex items-center gap-2"><Database className="w-3.5 h-3.5" /> History</h3>
                  <button onClick={loadAnalyzedJobs} className="text-on-surface-variant hover:text-primary"><RefreshCw className="w-3.5 h-3.5" /></button>
                </div>
                <div className="max-h-36 overflow-y-auto custom-scrollbar flex flex-col gap-2 pr-1">
                  {jobs.length === 0 ? (
                    <p className="text-[11px] text-on-surface-variant font-serif italic">No backend history yet.</p>
                  ) : jobs.slice(0, 6).map((job) => (
                    <button key={job.job_id} onClick={() => loadJob(job.job_id)} className={`text-left p-2 border rounded-[0.75rem] transition-colors ${analysisJob?.job_id === job.job_id ? 'border-outline-variant/70 bg-surface-container-high' : 'border-outline-variant/40 bg-surface-container hover:bg-surface-container-high'}`}>
                      <div className="flex justify-between items-start gap-2">
                        <span className="text-[11px] text-on-surface font-bold truncate">{job.filename}</span>
                        <span onClick={(e) => deleteJob(job.job_id, e)} className="text-on-surface-variant hover:text-rose-300"><Trash2 className="w-3.5 h-3.5" /></span>
                      </div>
                      <p className="text-[9px] text-on-surface-variant font-mono mt-1">{job.status} · {job.completed_pages}/{job.page_count} pages · {job.block_count} blocks</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-8 pt-4 border-t border-outline-variant/40">
              <button
                onClick={handleStartAnalysis}
                disabled={isAnalyzing}
                className={`w-full py-3.5 text-[10px] uppercase tracking-[0.25em] font-bold rounded-[0.75rem] flex items-center justify-center gap-2 select-none shadow-sm transition-all duration-150 h-12 ${
                  isAnalyzing
                    ? 'bg-surface-container text-on-surface-variant cursor-not-allowed border border-outline-variant/30'
                    : 'bg-primary text-on-primary hover:bg-primary/90 active:scale-[0.99] cursor-pointer'
                }`}
              >
                {isAnalyzing ? (
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-outline-variant/70 border-t-transparent rounded-full animate-spin" />
                    <span>{batchJobIds.length > 1 ? 'Analyzing Batch...' : 'Analyzing Layout...'}</span>
                  </div>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current text-on-primary" />
                    <span>{selectedFiles.length > 1 ? 'Start Batch Analysis' : 'Start Analysis'}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </aside>

        <section className="flex-1 relative bg-surface-container flex items-center justify-center overflow-hidden h-full">
          {isAnalyzing && (
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-30 flex flex-col items-center justify-center text-center p-6 select-none">
              <div className="bg-surface-container-lowest p-6 rounded-[0.75rem] border border-outline-variant/40 shadow-2xl flex flex-col items-center max-w-sm justify-center">
                <span className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4" />
                <h4 className="font-serif italic text-sm text-primary">Backend Layout Engine Processing</h4>
                <p className="text-xs text-on-surface-variant mt-2 animate-pulse leading-relaxed">{statusMessage}</p>
              </div>
            </div>
          )}

          {analysisJob?.pages?.length ? (
            <div className="absolute top-4 left-4 z-20 flex w-[260px] items-center gap-2 bg-surface-container-low/90 border border-outline-variant/40 px-3 py-2 text-[10px] font-mono text-on-surface-variant">
              <FileText className="h-3.5 w-3.5 shrink-0" />
              <button onClick={goToPreviousPage} disabled={currentPageIndex <= 0} className="flex h-6 w-6 shrink-0 items-center justify-center text-on-surface-variant hover:text-primary disabled:cursor-not-allowed disabled:text-on-surface-variant/40" title="上一页">
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <select value={currentPageIndex} onChange={(e) => goToPage(Number(e.target.value))} className="min-w-0 flex-1 bg-transparent text-primary focus:outline-none">
                {analysisJob.pages.map((page, idx) => (
                  <option key={page.page_id} value={idx}>Page {page.page_id + 1} · {page.status || 'pending'}</option>
                ))}
              </select>
              <button onClick={goToNextPage} disabled={currentPageIndex >= availablePageCount - 1} className="flex h-6 w-6 shrink-0 items-center justify-center text-on-surface-variant hover:text-primary disabled:cursor-not-allowed disabled:text-on-surface-variant/40" title="下一页">
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : selectedFiles.length > 0 ? (
            <div className="absolute top-4 left-4 z-20 bg-surface-container-low/90 border border-outline-variant/40 px-3 py-2 text-[10px] font-mono text-on-surface-variant">
              {selectedFileSummary} ready for backend analysis
            </div>
          ) : null}

          <div className="overflow-auto max-w-full max-h-full p-12 flex items-center justify-center custom-scrollbar w-full h-full">
            <motion.div
              className="relative bg-surface-bright shadow-2xl rounded-[0.75rem] transition-all overflow-hidden cursor-crosshair border border-outline-variant/40"
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
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-surface-container text-center p-8 text-on-surface-variant">
                  <FileText className="w-10 h-10 mb-3" />
                  <p className="text-lg font-semibold text-on-surface-variant">Select PDF files and start analysis</p>
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
                    <div className="absolute text-[9px] px-2 py-0.5 rounded-[0.75rem] text-white font-mono uppercase tracking-wider whitespace-nowrap -top-5 -left-[2px]" style={{ backgroundColor: colors.border }}>
                      {seg.level ? `${seg.level} · ` : ''}{BLOCK_TYPE_LABELS[seg.type]}
                    </div>
                    <button onClick={(e) => handleDeleteSegment(seg.id, e)} className="absolute top-1 right-1 z-20 rounded-[0.75rem] border border-outline-variant/40 bg-primary/80 p-1 text-on-primary opacity-0 shadow transition-opacity hover:bg-rose-600 group-hover:opacity-100">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })}

              {isDrawing && canvasContainerRef.current && (
                <div className="absolute border-2 border-dashed border-primary bg-primary/10 pointer-events-none z-30" style={{ left: `${Math.min(startPos.x, currentDragPos.x)}px`, top: `${Math.min(startPos.y, currentDragPos.y)}px`, width: `${Math.abs(currentDragPos.x - startPos.x)}px`, height: `${Math.abs(currentDragPos.y - startPos.y)}px` }} />
              )}
            </motion.div>
          </div>

          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 bg-surface-container-low/90 border border-outline-variant/40 backdrop-blur-md px-5 py-2.5 flex items-center gap-3 shadow-2xl z-25 select-none rounded-[0.75rem] text-primary ">
            <button onClick={handleUndo} disabled={historyPointer <= 0} className={`p-2 rounded-[0.75rem] transition-colors flex items-center justify-center ${historyPointer <= 0 ? 'text-on-surface-variant/40' : 'text-primary hover:bg-surface-container'}`} title="Undo Action"><Undo2 className="w-4 h-4" /></button>
            <button onClick={handleRedo} disabled={historyPointer >= history.length - 1} className={`p-2 rounded-[0.75rem] transition-colors flex items-center justify-center ${historyPointer >= history.length - 1 ? 'text-on-surface-variant/40' : 'text-primary hover:bg-surface-container'}`} title="Redo Action"><Redo2 className="w-4 h-4" /></button>
            <div className="w-px h-5 bg-surface-container-high mx-1" />
            <button onClick={goToPreviousPage} disabled={!availablePageCount || currentPageIndex <= 0} className={`p-2 rounded-[0.75rem] transition-colors flex items-center justify-center ${!availablePageCount || currentPageIndex <= 0 ? 'text-on-surface-variant/40' : 'text-on-surface-variant hover:text-primary hover:bg-surface-container'}`} title="上一页"><ChevronLeft className="w-4 h-4" /></button>
            <span className="w-[72px] shrink-0 text-center text-[10px] font-mono font-bold text-primary">
              {availablePageCount ? `${currentPageIndex + 1}/${availablePageCount}` : '-/-'}
            </span>
            <button onClick={goToNextPage} disabled={!availablePageCount || currentPageIndex >= availablePageCount - 1} className={`p-2 rounded-[0.75rem] transition-colors flex items-center justify-center ${!availablePageCount || currentPageIndex >= availablePageCount - 1 ? 'text-on-surface-variant/40' : 'text-on-surface-variant hover:text-primary hover:bg-surface-container'}`} title="下一页"><ChevronRight className="w-4 h-4" /></button>
            <div className="w-px h-5 bg-surface-container-high mx-1" />
            <button onClick={handleZoomOut} className="p-2 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-[0.75rem] transition-colors flex items-center justify-center" title="Zoom Out"><ZoomOut className="w-4 h-4" /></button>
            <span className="text-[10px] font-mono font-bold text-primary min-w-[40px] text-center">{Math.round(scale * 100)}%</span>
            <button onClick={handleZoomIn} className="p-2 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-[0.75rem] transition-colors flex items-center justify-center" title="Zoom In"><ZoomIn className="w-4 h-4" /></button>
            <div className="w-px h-5 bg-surface-container-high mx-1" />
            <button onClick={handleResetZoom} className="p-2 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-[0.75rem] transition-colors flex items-center justify-center" title="Reset Zoom to Fit"><Maximize2 className="w-4 h-4" /></button>
          </div>
        </section>

        <aside className="w-[380px] h-full flex flex-col border-l border-outline-variant/40 bg-surface-container-low z-20 flex-shrink-0 text-on-surface">
          <div className="flex border-b border-outline-variant/40 pt-4 px-4 bg-surface-container-low">
            <button onClick={() => setActiveTab('list')} className={`flex-1 pb-3 text-[10px] uppercase tracking-wider font-bold flex items-center justify-center gap-2 border-b-2 transition-all cursor-pointer ${activeTab === 'list' ? 'text-primary border-primary' : 'text-on-surface-variant hover:text-primary border-transparent'}`}>
              <List className="w-4 h-4" /><span>Blocks Identified</span>
            </button>
            <button onClick={() => setActiveTab('json')} className={`flex-1 pb-3 text-[10px] uppercase tracking-wider font-bold flex items-center justify-center gap-2 border-b-2 transition-all cursor-pointer ${activeTab === 'json' ? 'text-primary border-primary' : 'text-on-surface-variant hover:text-primary border-transparent'}`}>
              <Code2 className="w-4 h-4" /><span>JSON Payload</span>
            </button>
          </div>

          <div className="p-4 border-b border-outline-variant/30 bg-surface-container text-xs text-on-surface-variant">
            <div className="grid grid-cols-3 gap-2 mb-3">
              <div className="border border-outline-variant/40 bg-surface-container p-2"><b className="block text-primary text-base font-mono">{displayedPageCount || '-'}</b><span className="text-[9px] uppercase tracking-wider">Pages</span></div>
              <div className="border border-outline-variant/40 bg-surface-container p-2"><b className="block text-primary text-base font-mono">{visibleSegments.length}</b><span className="text-[9px] uppercase tracking-wider">Blocks</span></div>
              <div className="border border-outline-variant/40 bg-surface-container p-2"><b className="block text-primary text-base font-mono">{analysisJob?.errors?.length || 0}</b><span className="text-[9px] uppercase tracking-wider">Errors</span></div>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-mono">{currentPageSegments.length} blocks on current page</span>
              <button onClick={handleClearAll} className="hover:underline font-bold text-on-surface cursor-pointer">Clear Local Map</button>
            </div>
          </div>

          <div className="flex-grow overflow-y-auto custom-scrollbar p-4 bg-surface-container-low">
            <AnimatePresence mode="wait">
              {activeTab === 'list' ? (
                <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} className="flex flex-col gap-3">
                  {currentPageSegments.length === 0 ? (
                    <div className="text-center py-16 px-4">
                      <AlertTriangle className="w-8 h-8 mx-auto text-on-surface-variant mb-3" />
                      <p className="text-on-surface-variant text-xs">No backend blocks matching the current filters on this page.</p>
                      <button onClick={handleStartAnalysis} className="mt-4 text-xs font-bold underline text-on-surface hover:text-primary">Run backend analysis</button>
                    </div>
                  ) : currentPageSegments.map((seg) => {
                    const colors = getColorSchema(seg.type);
                    const isSelected = selectedSegmentId === seg.id;
                    return (
                      <div key={seg.id} onMouseEnter={() => setSelectedSegmentId(seg.id)} onMouseLeave={() => setSelectedSegmentId(null)} className={`bg-surface-container-lowest border p-3.5 flex flex-col gap-2.5 transition-all cursor-pointer relative group rounded-[0.75rem] ${isSelected ? 'border-primary/50 bg-surface-container shadow-lg ' : 'border-outline-variant/30 hover:border-outline-variant/40'}`}>
                        <div className="flex justify-between items-center">
                          <div className="flex items-center gap-2 select-none">
                            <div className="w-1.5 h-1.5 rounded-[0.75rem]" style={{ backgroundColor: colors.border }} />
                            <span className="text-[10px] font-mono font-bold text-primary uppercase tracking-wider">{seg.level ? `${seg.level} · ` : ''}{BLOCK_TYPE_LABELS[seg.type]}</span>
                          </div>
                          <span className="text-[9px] font-mono bg-surface-container-high px-1.5 py-0.5 rounded-[0.75rem] text-on-surface border border-outline-variant/30 font-bold">p{(seg.pageId || 0) + 1}</span>
                        </div>
                        {seg.type === 'table' ? (
                          <div className="flex items-center gap-2 bg-surface-container p-2 rounded-[0.75rem] text-xs text-on-surface font-medium border border-outline-variant/30"><Table className="w-4 h-4 text-on-surface-variant" /><span className="truncate font-serif italic text-on-surface-variant">{seg.text}</span></div>
                        ) : seg.type === 'chart' ? (
                          <div className="space-y-1 rounded-[0.75rem] border border-outline-variant/30 bg-surface-container p-2 text-xs">
                            <p className="truncate font-serif italic text-on-surface-variant">{seg.text}</p>
                            {seg.chartDescription ? <p className="line-clamp-2 text-on-surface-variant">{seg.chartDescription}</p> : null}
                          </div>
                        ) : seg.type === 'image' ? (
                          <div className="flex items-center gap-2 bg-surface-container p-2 rounded-[0.75rem] text-xs text-on-surface font-medium border border-outline-variant/30"><ImageIcon className="w-4 h-4 text-on-surface-variant" /><span className="truncate font-serif italic text-on-surface-variant">{seg.text}</span></div>
                        ) : (
                          <p className="text-xs text-on-surface-variant leading-relaxed line-clamp-3 font-sans">{seg.text}</p>
                        )}
                        <button onClick={(e) => handleDeleteSegment(seg.id, e)} className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 text-on-surface-variant hover:text-rose-500 font-bold transition-all p-1 rounded-[0.75rem] hover:bg-surface-container"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    );
                  })}
                </motion.div>
              ) : (
                <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} className="h-full flex flex-col gap-2 font-mono text-[11px]">
                  <div className="relative">
                    <pre className="bg-surface-container-lowest text-on-surface-variant p-4 rounded-[0.75rem] border border-outline-variant/40 overflow-x-auto select-text custom-scrollbar leading-relaxed"><code className="text-on-surface">{getJsonRepresentation()}</code></pre>
                    <button onClick={() => { navigator.clipboard.writeText(getJsonRepresentation()); alert('JSON mappings copied to clipboard!'); }} className="absolute top-2 right-2 px-2.5 py-1 text-[9px] uppercase tracking-wider font-bold bg-surface-container border border-outline-variant/40 text-on-surface hover:bg-primary hover:text-on-primary rounded-[0.75rem] transition-colors">Copy</button>
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
            <div className="bg-surface-container-lowest rounded-[0.75rem] p-6 max-w-sm w-full border border-outline-variant/40 shadow-2xl relative text-primary">
              <h3 className="font-serif italic text-base text-primary mb-4">Annotate Backend Block</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-[9px] font-mono font-bold uppercase tracking-wider text-on-surface-variant mb-1">Block Classification</label>
                  <select value={newBoxType} onChange={(e) => setNewBoxType(e.target.value as BackendBlockType)} className="w-full px-3 py-1.5 bg-surface-container-low border border-outline-variant/40 rounded-[0.75rem] text-xs font-serif italic text-primary focus:outline-none focus:border-outline-variant/70">
                    {BLOCK_TYPES.map((type) => <option key={type} value={type}>{BLOCK_TYPE_LABELS[type]}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[9px] font-mono font-bold uppercase tracking-wider text-on-surface-variant mb-1">Transcription</label>
                  <input type="text" required placeholder="Transcribe block text or descriptive name..." value={newBoxText} onChange={(e) => setNewBoxText(e.target.value)} className="w-full px-3 py-1.5 bg-surface-container-low border border-outline-variant/40 rounded-[0.75rem] text-xs text-primary placeholder:text-on-surface-variant focus:outline-none focus:border-outline-variant/70" />
                </div>
                <div className="bg-surface-container p-3 rounded-[0.75rem] border border-outline-variant/30 text-[10px] text-on-surface-variant font-mono">
                  <span className="block font-bold text-on-surface-variant mb-0.5 uppercase tracking-wider">Calculated Bounding Box</span>
                  <span>Top: {drawnBoxPercent[0]}%, Left: {drawnBoxPercent[1]}%, Width: {drawnBoxPercent[2]}%, Height: {drawnBoxPercent[3]}%</span>
                </div>
              </div>
              <div className="mt-5 flex justify-end gap-3 pt-3 border-t border-outline-variant/40">
                <button onClick={() => { setNewBoxModalOpen(false); setDrawnBoxPercent(null); }} className="px-3.5 py-1.5 text-[10px] uppercase tracking-wider font-bold border border-outline-variant/40 hover:bg-surface-container rounded-[0.75rem] text-on-surface cursor-pointer">Cancel</button>
                <button onClick={handleCreateDrawnBox} className="px-4 py-1.5 text-[10px] uppercase tracking-wider font-bold bg-primary text-on-primary hover:bg-primary/90 rounded-[0.75rem] cursor-pointer">Create Label</button>
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

function isBackendJobComplete(status: string) {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'complete' || normalized === 'completed' || normalized === 'done';
}
