/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  Check,
  Copy,
  FileImage,
  HelpCircle,
  Maximize2,
  MousePointer2,
  Plus,
  Redo2,
  Save,
  Trash2,
  Undo2,
  Upload,
  ZoomIn,
  ZoomOut,
  Image as ImageIcon,
  ChevronLeft,
  ChevronRight,
  Tags,
  Edit2,
  X
} from 'lucide-react';
import { BoundingBoxAnnotation, BoundingBoxImage, BoundingBoxJob, BoundingBoxLabel } from '../types';

interface BoundingBoxWorkspaceProps {
  datasetId: string;
  onGoBack: () => void;
}

interface DragState {
  mode: 'draw' | 'move' | 'resize';
  blockId?: string;
  startX: number;
  startY: number;
  original?: [number, number, number, number];
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export default function BoundingBoxWorkspace({ datasetId, onGoBack }: BoundingBoxWorkspaceProps) {
  const [job, setJob] = useState<BoundingBoxJob | null>(null);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [history, setHistory] = useState<Array<Record<string, BoundingBoxAnnotation[]>>>([]);
  const [historyPointer, setHistoryPointer] = useState(-1);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [selectedLabelId, setSelectedLabelId] = useState<string>('');
  const [isCreating, setIsCreating] = useState(false);
  const [showLabelManager, setShowLabelManager] = useState(false);
  const [editingLabel, setEditingLabel] = useState<BoundingBoxLabel | null>(null);
  const [newLabelName, setNewLabelName] = useState('');
  const [newLabelColor, setNewLabelColor] = useState('#FF6B6B');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const images = job?.images || [];
  const currentImage = images[currentImageIndex] || null;
  const annotations = job?.annotations || {};
  const currentAnnotations = currentImage ? (annotations[currentImage.id] || []) : [];
  const selectedAnnotation = currentAnnotations.find(a => a.id === selectedAnnotationId) || null;
  const labels = job?.labels || [];
  const canvasWidth = 800;
  const [canvasHeight, setCanvasHeight] = useState(600);
  const [imageLoaded, setImageLoaded] = useState(false);

  useEffect(() => {
    if (!currentImage?.image_url) return;
    const img = new Image();
    img.onload = () => {
      const height = Math.round(canvasWidth * (img.naturalHeight / Math.max(img.naturalWidth, 1)));
      setCanvasHeight(height);
      setImageLoaded(true);
    };
    img.src = currentImage.image_url;
  }, [currentImage?.image_url]);

  useEffect(() => {
    loadJob();
  }, [datasetId]);

  useEffect(() => {
    if (labels.length > 0 && !selectedLabelId) {
      setSelectedLabelId(labels[0].id);
    }
  }, [labels, selectedLabelId]);

  async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.error) throw new Error(body.error || `HTTP ${response.status}`);
    return body as T;
  }

  async function loadJob() {
    setError('');
    try {
      const data = await fetchJson<BoundingBoxJob>(`/api/bounding-box/datasets/${datasetId}/job`);
      setJob(data);
      setHistory([data.annotations || {}]);
      setHistoryPointer(0);
      if (data.images.length > 0) {
        setCurrentImageIndex(0);
        const firstAnnotations = data.annotations[data.images[0].id] || [];
        setSelectedAnnotationId(firstAnnotations[0]?.id || null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function record(nextAnnotations: Record<string, BoundingBoxAnnotation[]>) {
    setJob((current) => current ? { ...current, annotations: nextAnnotations } : current);
    const nextHistory = history.slice(0, historyPointer + 1).concat([nextAnnotations]);
    setHistory(nextHistory);
    setHistoryPointer(nextHistory.length - 1);
  }

  function updateAnnotations(imageId: string, newAnnotations: BoundingBoxAnnotation[]) {
    const nextAnnotations = { ...annotations, [imageId]: newAnnotations };
    record(nextAnnotations);
  }

  function addAnnotation(bbox: [number, number, number, number]) {
    if (!currentImage || !selectedLabelId) return;
    const label = labels.find(l => l.id === selectedLabelId);
    if (!label) return;

    const id = `ann_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const annotation: BoundingBoxAnnotation = {
      id,
      image_id: currentImage.id,
      label_id: selectedLabelId,
      label_name: label.name,
      bbox,
      notes: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    updateAnnotations(currentImage.id, [...currentAnnotations, annotation]);
    setSelectedAnnotationId(id);
  }

  function updateAnnotation(annotationId: string, updates: Partial<BoundingBoxAnnotation>) {
    const nextAnnotations = currentAnnotations.map(ann =>
      ann.id === annotationId
        ? { ...ann, ...updates, updated_at: new Date().toISOString() }
        : ann
    );
    updateAnnotations(currentImage.id, nextAnnotations);
  }

  function deleteAnnotation(annotationId: string) {
    updateAnnotations(currentImage.id, currentAnnotations.filter(a => a.id !== annotationId));
    if (selectedAnnotationId === annotationId) {
      setSelectedAnnotationId(null);
    }
  }

  function getCanvasPoint(event: React.PointerEvent) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || !currentImage) return null;
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    return { x: clamp(x, 0, 100), y: clamp(y, 0, 100) };
  }

  function handleCanvasPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!currentImage || event.target !== event.currentTarget) return;
    if (!isCreating) return;
    const point = getCanvasPoint(event);
    if (!point) return;
    setDragState({ mode: 'draw', startX: point.x, startY: point.y });
  }

  function handleAnnotationPointerDown(event: React.PointerEvent, annotation: BoundingBoxAnnotation, mode: 'move' | 'resize') {
    event.stopPropagation();
    const point = getCanvasPoint(event);
    if (!point) return;
    setSelectedAnnotationId(annotation.id);
    setDragState({ mode, blockId: annotation.id, startX: point.x, startY: point.y, original: annotation.bbox });
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragState || !currentImage) return;
    const point = getCanvasPoint(event);
    if (!point) return;

    if (dragState.mode === 'draw') return;

    const dx = point.x - dragState.startX;
    const dy = point.y - dragState.startY;
    const annotation = currentAnnotations.find(a => a.id === dragState.blockId);
    if (!annotation || !dragState.original) return;

    const [px1, py1, px2, py2] = dragState.original;

    if (dragState.mode === 'move') {
      const newBbox: [number, number, number, number] = [
        clamp(px1 + dx, 0, 100 - (px2 - px1)),
        clamp(py1 + dy, 0, 100 - (py2 - py1)),
        clamp(px2 + dx, px1 + 1, 100),
        clamp(py2 + dy, py1 + 1, 100),
      ];
      updateAnnotation(annotation.id, { bbox: newBbox });
    } else if (dragState.mode === 'resize') {
      const newBbox: [number, number, number, number] = [
        px1,
        py1,
        clamp(px2 + dx, px1 + 1, 100),
        clamp(py2 + dy, py1 + 1, 100),
      ];
      updateAnnotation(annotation.id, { bbox: newBbox });
    }
  }

  function handlePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragState || !currentImage) return;
    const point = getCanvasPoint(event);

    if (point && dragState.mode === 'draw') {
      const x1 = Math.min(dragState.startX, point.x);
      const y1 = Math.min(dragState.startY, point.y);
      const x2 = Math.max(dragState.startX, point.x);
      const y2 = Math.max(dragState.startY, point.y);
      if (x2 - x1 > 1 && y2 - y1 > 1) {
        addAnnotation([x1, y1, x2, y2]);
      }
    }
    setDragState(null);
  }

  function undo() {
    if (historyPointer <= 0 || !job) return;
    const nextPointer = historyPointer - 1;
    setHistoryPointer(nextPointer);
    setJob({ ...job, annotations: history[nextPointer] });
  }

  function redo() {
    if (historyPointer >= history.length - 1 || !job) return;
    const nextPointer = historyPointer + 1;
    setHistoryPointer(nextPointer);
    setJob({ ...job, annotations: history[nextPointer] });
  }

  async function saveDraft() {
    if (!job) return;
    try {
      setError('');
      await fetchJson(`/api/bounding-box/datasets/${datasetId}/draft`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ annotations: job.annotations }),
      });
      setMessage('草稿已保存');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function submitVersion() {
    if (!job) return;
    try {
      setError('');
      await fetchJson(`/api/bounding-box/datasets/${datasetId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ annotations: job.annotations }),
      });
      setMessage('版本已提交');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleImageUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    try {
      setError('');
      setMessage('正在上传图片...');

      const formData = new FormData();
      for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
      }

      const response = await fetch(`/api/bounding-box/datasets/${datasetId}/images`, {
        method: 'POST',
        body: formData,
      });

      const body = await response.json().catch(() => ({}));
      if (!response.ok || body.error) throw new Error(body.error || `HTTP ${response.status}`);

      setMessage(`已上传 ${body.added?.length || 0} 张图片`);
      await loadJob();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  function getLabelColor(labelId: string): string {
    const label = labels.find(l => l.id === labelId);
    return label?.color || '#A9A9A9';
  }

  async function createLabel() {
    if (!newLabelName.trim()) return;
    try {
      const response = await fetch(`/api/bounding-box/datasets/${datasetId}/labels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newLabelName.trim(), color: newLabelColor }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
      setNewLabelName('');
      setNewLabelColor('#FF6B6B');
      await loadJob();
      setMessage('标签已创建');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function updateLabel(labelId: string) {
    if (!newLabelName.trim()) return;
    try {
      const response = await fetch(`/api/bounding-box/datasets/${datasetId}/labels/${labelId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newLabelName.trim(), color: newLabelColor }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
      setEditingLabel(null);
      setNewLabelName('');
      setNewLabelColor('#FF6B6B');
      await loadJob();
      setMessage('标签已更新');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function deleteLabel(labelId: string) {
    try {
      const response = await fetch(`/api/bounding-box/datasets/${datasetId}/labels/${labelId}`, {
        method: 'DELETE',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
      await loadJob();
      if (selectedLabelId === labelId) {
        setSelectedLabelId(labels.find(l => l.id !== labelId)?.id || '');
      }
      setMessage('标签已删除');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function startEditLabel(label: BoundingBoxLabel) {
    setEditingLabel(label);
    setNewLabelName(label.name);
    setNewLabelColor(label.color);
  }

  function cancelEdit() {
    setEditingLabel(null);
    setNewLabelName('');
    setNewLabelColor('#FF6B6B');
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[#0c0c0c] text-white/80">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-[#0c0c0c] px-6">
        <div className="flex items-center gap-4">
          <button onClick={onGoBack} className="p-2 text-white/60 hover:bg-white/10" aria-label="返回">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-sm font-semibold">{job?.dataset_name || datasetId}</h1>
            <p className="text-[11px] text-white/40">物体画框标注</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ToolbarButton icon={<Save className="h-4 w-4" />} label="保存草稿" onClick={saveDraft} />
          <ToolbarButton icon={<Check className="h-4 w-4" />} label="提交版本" onClick={submitVersion} primary />
          <ToolbarButton icon={<Undo2 className="h-4 w-4" />} label="撤销" onClick={undo} disabled={historyPointer <= 0} />
          <ToolbarButton icon={<Redo2 className="h-4 w-4" />} label="重做" onClick={redo} disabled={historyPointer >= history.length - 1} />
          <ToolbarButton icon={<HelpCircle className="h-4 w-4" />} label="快捷键" onClick={() => alert('拖拽空白区域添加选框；拖拽选框移动；拖拽右下角调整大小；右侧面板修改 label 和备注。')} />
        </div>
      </header>

      {message && !error && (
        <div className="border-b border-green-500/30 bg-green-500/10 px-6 py-2 text-xs font-semibold text-green-400">
          {message}
        </div>
      )}

      {error && (
        <div className="border-b border-red-500/30 bg-red-500/10 px-6 py-2 text-xs font-semibold text-red-400">
          {error}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className="w-56 shrink-0 overflow-y-auto border-r border-white/10 bg-[#0f0f0f] p-4">
          <div className="mb-4">
            <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/40">图片列表</h2>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="mb-3 flex w-full items-center justify-center gap-2 rounded border border-dashed border-white/20 bg-white/5 px-3 py-2 text-xs text-white/60 hover:bg-white/10"
            >
              <Upload className="h-4 w-4" />
              上传图片
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleImageUpload}
              className="hidden"
            />
          </div>
          <div className="space-y-2">
            {images.map((img, index) => (
              <button
                key={img.id}
                onClick={() => {
                  setCurrentImageIndex(index);
                  setSelectedAnnotationId(annotations[img.id]?.[0]?.id || null);
                }}
                className={`flex w-full items-center gap-3 border p-2 text-left ${index === currentImageIndex ? 'border-cyan-400/50 bg-cyan-400/10' : 'border-white/10 bg-[#0c0c0c] hover:bg-white/5'}`}
              >
                <div className="h-12 w-12 shrink-0 overflow-hidden bg-white/5">
                  <img src={img.image_url} alt={img.filename} className="h-full w-full object-cover" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-white/80">{img.filename}</p>
                  <p className="text-[10px] text-white/40">{annotations[img.id]?.length || 0} 标注</p>
                </div>
              </button>
            ))}
            {images.length === 0 && (
              <div className="py-8 text-center text-xs text-white/40">
                <ImageIcon className="mx-auto mb-2 h-8 w-8 opacity-50" />
                <p>暂无图片</p>
                <p>点击上方按钮上传</p>
              </div>
            )}
          </div>
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col bg-[#141414]">
          <div className="absolute left-4 top-4 z-20 flex items-center gap-2 border border-white/10 bg-black/50 px-3 py-2 text-xs text-white/60">
            <MousePointer2 className="h-4 w-4" />
            <span>{isCreating ? '点击拖拽创建选框' : '点击"创建"按钮开始绘制'}</span>
          </div>

          <div className="absolute left-4 top-4 z-20 flex items-center gap-2 mt-10">
            <button
              onClick={() => setCurrentImageIndex(Math.max(0, currentImageIndex - 1))}
              disabled={currentImageIndex <= 0}
              className="p-2 border border-white/10 bg-black/50 disabled:opacity-30 hover:bg-white/10"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-2 text-xs text-white/60">
              {currentImageIndex + 1} / {images.length}
            </span>
            <button
              onClick={() => setCurrentImageIndex(Math.min(images.length - 1, currentImageIndex + 1))}
              disabled={currentImageIndex >= images.length - 1}
              className="p-2 border border-white/10 bg-black/50 disabled:opacity-30 hover:bg-white/10"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="flex flex-1 items-center justify-center overflow-auto p-12">
            {currentImage ? (
              <div
                ref={canvasRef}
                onPointerDown={handleCanvasPointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                className={`relative shrink-0 bg-cover bg-center shadow-2xl ${isCreating ? 'cursor-crosshair' : 'cursor-default'}`}
                style={{
                  width: canvasWidth,
                  height: canvasHeight,
                  transform: `scale(${scale})`,
                  transformOrigin: 'center',
                  backgroundImage: `url("${currentImage.image_url}")`,
                }}
              >
                {currentAnnotations.map((annotation) => {
                  const [x1, y1, x2, y2] = annotation.bbox;
                  const selected = annotation.id === selectedAnnotationId;
                  const color = getLabelColor(annotation.label_id);
                  return (
                    <div
                      key={annotation.id}
                      onPointerDown={(e) => !isCreating && handleAnnotationPointerDown(e, annotation, 'move')}
                      className={`absolute border-2 ${selected ? 'shadow-lg' : 'opacity-80'}`}
                      style={{
                        left: `${x1}%`,
                        top: `${y1}%`,
                        width: `${x2 - x1}%`,
                        height: `${y2 - y1}%`,
                        borderColor: color,
                        backgroundColor: `${color}20`,
                      }}
                    >
                      <span
                        className="absolute -top-6 left-0 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                        style={{ backgroundColor: color }}
                      >
                        {annotation.label_name}
                      </span>
                      {!isCreating && (
                        <button
                          type="button"
                          onPointerDown={(e) => handleAnnotationPointerDown(e, annotation, 'resize')}
                          className="absolute bottom-0 right-0 h-3 w-3 cursor-se-resize"
                          style={{ backgroundColor: color }}
                          aria-label="调整大小"
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-white/40">
                {images.length === 0 ? '请上传图片开始标注' : '正在加载...'}
              </div>
            )}
          </div>

          <div className="absolute bottom-6 left-1/2 flex -translate-x-1/2 items-center gap-2 border border-white/10 bg-black/50 px-4 py-2">
            <button onClick={() => setScale((v) => Math.max(0.3, v - 0.1))} className="p-2 text-white/60 hover:bg-white/10">
              <ZoomOut className="h-4 w-4" />
            </button>
            <span className="w-12 text-center text-xs">{Math.round(scale * 100)}%</span>
            <button onClick={() => setScale((v) => Math.min(2, v + 0.1))} className="p-2 text-white/60 hover:bg-white/10">
              <ZoomIn className="h-4 w-4" />
            </button>
            <button onClick={() => setScale(1)} className="p-2 text-white/60 hover:bg-white/10">
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        </main>

        <aside className="w-72 shrink-0 overflow-y-auto border-l border-white/10 bg-[#0f0f0f] p-4">
          <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/40">标注工具</h2>
          <button
            onClick={() => setIsCreating(!isCreating)}
            className={`mb-4 flex w-full items-center justify-center gap-2 rounded px-3 py-2 text-xs font-semibold transition-colors ${
              isCreating
                ? 'bg-cyan-500 text-white'
                : 'border border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/10'
            }`}
          >
            <Plus className="h-4 w-4" />
            {isCreating ? '完成创建' : '创建选框'}
          </button>

          <div className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              <label className="text-[10px] font-semibold uppercase tracking-wider text-white/40">选择标签</label>
              <button
                onClick={() => setShowLabelManager(!showLabelManager)}
                className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-cyan-400 hover:bg-cyan-500/10"
              >
                <Tags className="h-3 w-3" />
                管理
              </button>
            </div>
            {showLabelManager && (
              <div className="mb-3 rounded border border-cyan-500/30 bg-cyan-500/5 p-3">
                <h3 className="mb-2 text-xs font-semibold text-cyan-400">标签管理</h3>
                <div className="mb-3 space-y-2">
                  <input
                    type="text"
                    value={newLabelName}
                    onChange={(e) => setNewLabelName(e.target.value)}
                    placeholder="标签名称"
                    className="w-full border border-white/10 bg-[#0c0c0c] px-2 py-1 text-xs text-white outline-none focus:border-cyan-500/50"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        editingLabel ? updateLabel(editingLabel.id) : createLabel();
                      }
                    }}
                  />
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={newLabelColor}
                      onChange={(e) => setNewLabelColor(e.target.value)}
                      className="h-8 w-12 cursor-pointer rounded border border-white/10 bg-transparent"
                    />
                    <input
                      type="text"
                      value={newLabelColor}
                      onChange={(e) => setNewLabelColor(e.target.value)}
                      className="flex-1 border border-white/10 bg-[#0c0c0c] px-2 py-1 text-xs text-white outline-none focus:border-cyan-500/50"
                    />
                  </div>
                  <div className="flex gap-2">
                    {editingLabel ? (
                      <>
                        <button
                          onClick={() => updateLabel(editingLabel.id)}
                          className="flex-1 rounded bg-cyan-500 px-2 py-1 text-xs font-semibold text-white hover:bg-cyan-600"
                        >
                          保存
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="flex-1 rounded border border-white/10 px-2 py-1 text-xs text-white/60 hover:bg-white/5"
                        >
                          取消
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={createLabel}
                        className="flex-1 rounded bg-cyan-500 px-2 py-1 text-xs font-semibold text-white hover:bg-cyan-600"
                      >
                        添加
                      </button>
                    )}
                  </div>
                </div>
                <div className="max-h-48 space-y-1 overflow-y-auto">
                  {labels.map((label) => (
                    <div
                      key={label.id}
                      className="flex items-center justify-between rounded bg-[#0c0c0c] px-2 py-1.5"
                    >
                      <div className="flex items-center gap-2">
                        <span className="h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: label.color }} />
                        <span className="text-xs text-white/80">{label.name}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => startEditLabel(label)}
                          className="p-1 text-white/40 hover:text-white"
                        >
                          <Edit2 className="h-3 w-3" />
                        </button>
                        <button
                          onClick={() => deleteLabel(label.id)}
                          className="p-1 text-white/40 hover:text-red-400"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              {labels.map((label) => (
                <button
                  key={label.id}
                  onClick={() => setSelectedLabelId(label.id)}
                  className={`flex items-center gap-2 rounded border px-2 py-1.5 text-xs ${
                    selectedLabelId === label.id
                      ? 'border-white/30 bg-white/10 text-white'
                      : 'border-white/10 text-white/60 hover:bg-white/5'
                  }`}
                >
                  <span className="h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: label.color }} />
                  <span className="truncate">{label.name}</span>
                </button>
              ))}
            </div>
          </div>

          <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/40">选框属性</h2>
          {selectedAnnotation ? (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-white/40">标签</label>
                <select
                  value={selectedAnnotation.label_id}
                  onChange={(e) => {
                    const label = labels.find(l => l.id === e.target.value);
                    if (label) {
                      updateAnnotation(selectedAnnotation.id, { label_id: e.target.value, label_name: label.name });
                    }
                  }}
                  className="w-full border border-white/10 bg-[#0c0c0c] px-3 py-2 text-sm text-white outline-none focus:border-cyan-500/50"
                >
                  {labels.map((label) => (
                    <option key={label.id} value={label.id}>{label.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-white/40">备注</label>
                <textarea
                  value={selectedAnnotation.notes || ''}
                  onChange={(e) => updateAnnotation(selectedAnnotation.id, { notes: e.target.value })}
                  rows={4}
                  placeholder="添加备注..."
                  className="w-full resize-none border border-white/10 bg-[#0c0c0c] px-3 py-2 text-sm text-white outline-none focus:border-cyan-500/50"
                />
              </div>
              <div className="border border-white/10 bg-[#0c0c0c] p-3 text-[11px] text-white/40">
                <p>ID: {selectedAnnotation.id.slice(0, 20)}...</p>
                <p>BBox: [{selectedAnnotation.bbox.map(v => v.toFixed(1)).join(', ')}]%</p>
                <p>置信度: {selectedAnnotation.confidence ? `${(selectedAnnotation.confidence * 100).toFixed(0)}%` : 'N/A'}</p>
              </div>
              <button
                onClick={() => deleteAnnotation(selectedAnnotation.id)}
                className="flex w-full items-center justify-center gap-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-400 hover:bg-red-500/20"
              >
                <Trash2 className="h-4 w-4" />
                删除选框
              </button>
            </div>
          ) : (
            <div className="rounded border border-white/10 bg-[#0c0c0c] p-4 text-sm text-white/40">
              <Plus className="mb-2 h-5 w-5" />
              选择一个选框，或在画布空白处拖拽新增选框。
            </div>
          )}

          <div className="mt-6">
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-white/40">当前图片标注</h3>
            <div className="space-y-2">
              {currentAnnotations.map((annotation) => (
                <button
                  key={annotation.id}
                  onClick={() => setSelectedAnnotationId(annotation.id)}
                  className={`w-full border p-2 text-left text-xs ${
                    annotation.id === selectedAnnotationId
                      ? 'border-cyan-400/50 bg-cyan-400/10 text-white'
                      : 'border-white/10 bg-[#0c0c0c] text-white/60 hover:bg-white/5'
                  }`}
                >
                  <p className="flex items-center gap-2 font-semibold">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: getLabelColor(annotation.label_id) }} />
                    {annotation.label_name}
                  </p>
                  <p className="truncate text-white/40">{annotation.notes || annotation.id.slice(0, 16)}...</p>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function ToolbarButton({ icon, label, onClick, primary, disabled }: { icon: React.ReactNode; label: string; onClick: () => void; primary?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-2 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-30 ${
        primary
          ? 'rounded border border-cyan-500/50 bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30'
          : 'rounded border border-white/10 text-white/60 hover:bg-white/10 hover:text-white'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
