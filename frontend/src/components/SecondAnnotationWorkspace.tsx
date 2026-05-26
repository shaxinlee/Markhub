import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Check, Copy, FileText, HelpCircle, Maximize2, MousePointer2, Plus, Redo2, Save, Trash2, Undo2, ZoomIn, ZoomOut } from 'lucide-react';

interface AnnotationBlock {
  id: string;
  bbox: [number, number, number, number];
  label: string;
  block_type?: string;
  text: string;
  page_id: number;
  source?: string;
  modified?: boolean;
  modified_fields?: string[];
  updated_at?: string;
  updated_by?: string;
  weak_heading?: boolean;
  level?: 'H1' | 'H2' | 'H3' | null;
}

interface AnnotationPage {
  page_id: number;
  image_url: string;
  width: number;
  height: number;
  blocks: AnnotationBlock[];
}

interface AnnotationPayload {
  dataset_id: string;
  filename: string;
  pages: AnnotationPage[];
  label_types: string[];
  active_version?: string;
}

interface BackendBlock {
  id?: string;
  bbox?: [number, number, number, number];
  text?: string;
  page_id?: number;
  block_type?: string;
  label?: string;
  weak_heading?: boolean;
  level?: 'H1' | 'H2' | 'H3' | null;
}

interface BackendPage {
  page_id: number;
  image_url: string;
  width: number;
  height: number;
  blocks?: BackendBlock[];
}

interface BackendJob {
  job_id: string;
  filename: string;
  pages: BackendPage[];
}

interface SecondAnnotationWorkspaceProps {
  datasetId: string;
  onGoBack: () => void;
}

type DragMode = 'move' | 'resize' | 'draw';

const DEFAULT_LABEL_TYPES = [
  'doc_title',
  'title',
  'paragraph_title',
  'text',
  'table_of_contents',
  'handwriting',
  'table',
  'formula',
  'figure',
  'chart',
  'seal',
  'header',
  'footer',
  'footnote',
  'reference',
  'caption',
  'other',
];

function normalizeLabel(label: string) {
  return label === 'list' ? 'table_of_contents' : label;
}

function normalizeAnnotationPayload(payload: AnnotationPayload): AnnotationPayload {
  return {
    ...payload,
    label_types: payload.label_types?.length
      ? Array.from(new Set(payload.label_types.map(normalizeLabel).filter((label) => label !== 'list')))
      : DEFAULT_LABEL_TYPES,
    pages: (payload.pages || []).map((page) => ({
      ...page,
      blocks: (page.blocks || []).map((block) => {
        const label = normalizeLabel(block.label || block.block_type || 'text');
        return { ...block, label, block_type: label };
      }),
    })),
  };
}

export default function SecondAnnotationWorkspace({ datasetId, onGoBack }: SecondAnnotationWorkspaceProps) {
  const [payload, setPayload] = useState<AnnotationPayload | null>(null);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [scale, setScale] = useState(0.78);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [history, setHistory] = useState<AnnotationPage[][]>([]);
  const [historyPointer, setHistoryPointer] = useState(-1);
  const [dragState, setDragState] = useState<{
    mode: DragMode;
    blockId?: string;
    startX: number;
    startY: number;
    original?: [number, number, number, number];
  } | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const pages = payload?.pages || [];
  const currentPage = pages[currentPageIndex] || null;
  const selectedBlock = currentPage?.blocks.find((block) => block.id === selectedBlockId) || null;
  const labelTypes = payload?.label_types?.length
    ? Array.from(new Set(payload.label_types.map(normalizeLabel).filter((label) => label !== 'list')))
    : DEFAULT_LABEL_TYPES;
  const canvasWidth = 760;
  const canvasHeight = currentPage ? Math.round(canvasWidth * (currentPage.height / Math.max(currentPage.width, 1))) : 980;

  useEffect(() => {
    loadAnnotations();
  }, [datasetId]);

  async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.error) throw new Error(body.error || `HTTP ${response.status}`);
    return body as T;
  }

  async function loadAnnotations() {
    setError('');
    try {
      const data = normalizeAnnotationPayload(await loadAnnotationPayload());
      setPayload(data);
      setCurrentPageIndex(0);
      setSelectedBlockId(data.pages?.[0]?.blocks?.[0]?.id || null);
      setHistory([data.pages || []]);
      setHistoryPointer(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function loadAnnotationPayload(): Promise<AnnotationPayload> {
    try {
      return await fetchJson<AnnotationPayload>(`/api/datasets/${datasetId}/annotations`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (!message.includes('404') && !message.includes('dataset not found')) throw err;
      const job = await fetchJson<BackendJob>(`/api/jobs/${datasetId}/result`);
      setMessage('当前后端未提供二次标注读取接口，已从原始 Completed 结果临时加载。保存草稿/提交需要重启到最新后端。');
      return backendJobToAnnotationPayload(job);
    }
  }

  function backendJobToAnnotationPayload(job: BackendJob): AnnotationPayload {
    return {
      dataset_id: job.job_id || datasetId,
      filename: job.filename || datasetId,
      active_version: 'first_annotation',
      label_types: DEFAULT_LABEL_TYPES,
      pages: (job.pages || []).map((page) => ({
        page_id: page.page_id,
        image_url: page.image_url,
        width: page.width,
        height: page.height,
        blocks: (page.blocks || []).map((block, index) => {
          const label = normalizeLabel(block.label || block.block_type || 'text');
          return {
            id: String(block.id || `p${page.page_id.toString().padStart(3, '0')}_b${index.toString().padStart(3, '0')}`),
            bbox: block.bbox || [0, 0, 1, 1],
            label,
            block_type: label,
            text: block.text || '',
            page_id: block.page_id ?? page.page_id,
            source: 'model',
            modified: false,
            modified_fields: [],
            updated_at: '',
            updated_by: '',
            weak_heading: Boolean(block.weak_heading),
            level: block.level || null,
          };
        }),
      })),
    };
  }

  function record(nextPages: AnnotationPage[]) {
    setPayload((current) => current ? { ...current, pages: nextPages } : current);
    const nextHistory = history.slice(0, historyPointer + 1).concat([nextPages]);
    setHistory(nextHistory);
    setHistoryPointer(nextHistory.length - 1);
  }

  function updateCurrentPage(updater: (page: AnnotationPage) => AnnotationPage) {
    if (!payload || !currentPage) return;
    const nextPages = payload.pages.map((page, index) => index === currentPageIndex ? updater(page) : page);
    record(nextPages);
  }

  function markBlock(block: AnnotationBlock, fields: string[]): AnnotationBlock {
    const merged = new Set([...(block.modified_fields || []), ...fields]);
    return {
      ...block,
      modified: true,
      source: block.source === 'manual' ? 'manual' : 'human_verified',
      modified_fields: Array.from(merged),
      updated_at: new Date().toISOString(),
    };
  }

  function updateSelectedBlock(partial: Partial<AnnotationBlock>, fields: string[]) {
    if (!selectedBlockId) return;
    updateCurrentPage((page) => ({
      ...page,
      blocks: page.blocks.map((block) => block.id === selectedBlockId ? markBlock({ ...block, ...partial, block_type: partial.label || block.block_type }, fields) : block),
    }));
  }

  function deleteSelectedBlock() {
    if (!selectedBlockId) return;
    updateCurrentPage((page) => ({ ...page, blocks: page.blocks.filter((block) => block.id !== selectedBlockId) }));
    setSelectedBlockId(null);
  }

  function addBlock(bbox: [number, number, number, number]) {
    if (!currentPage) return;
    const id = `p${currentPage.page_id.toString().padStart(3, '0')}_manual_${Date.now()}`;
    const block: AnnotationBlock = {
      id,
      bbox,
      label: 'text',
      block_type: 'text',
      text: '',
      page_id: currentPage.page_id,
      source: 'manual',
      modified: true,
      modified_fields: ['bbox', 'label', 'text'],
      updated_at: new Date().toISOString(),
    };
    updateCurrentPage((page) => ({ ...page, blocks: [...page.blocks, block] }));
    setSelectedBlockId(id);
  }

  function canvasPoint(event: React.PointerEvent) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || !currentPage) return null;
    const x = clamp(((event.clientX - rect.left) / rect.width) * currentPage.width, 0, currentPage.width);
    const y = clamp(((event.clientY - rect.top) / rect.height) * currentPage.height, 0, currentPage.height);
    return { x, y };
  }

  function handleCanvasPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!currentPage || event.target !== event.currentTarget) return;
    const point = canvasPoint(event);
    if (!point) return;
    setDragState({ mode: 'draw', startX: point.x, startY: point.y });
  }

  function handleBlockPointerDown(event: React.PointerEvent<HTMLDivElement>, block: AnnotationBlock, mode: DragMode) {
    event.stopPropagation();
    const point = canvasPoint(event);
    if (!point) return;
    setSelectedBlockId(block.id);
    setDragState({ mode, blockId: block.id, startX: point.x, startY: point.y, original: block.bbox });
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragState || !currentPage) return;
    const point = canvasPoint(event);
    if (!point) return;
    if (dragState.mode === 'draw') return;
    const dx = point.x - dragState.startX;
    const dy = point.y - dragState.startY;
    updateCurrentPage((page) => ({
      ...page,
      blocks: page.blocks.map((block) => {
        if (block.id !== dragState.blockId || !dragState.original) return block;
        const [x1, y1, x2, y2] = dragState.original;
        const bbox: [number, number, number, number] = dragState.mode === 'move'
          ? [
              Math.round(clamp(x1 + dx, 0, page.width - 1)),
              Math.round(clamp(y1 + dy, 0, page.height - 1)),
              Math.round(clamp(x2 + dx, 1, page.width)),
              Math.round(clamp(y2 + dy, 1, page.height)),
            ]
          : [
              x1,
              y1,
              Math.round(clamp(x2 + dx, x1 + 4, page.width)),
              Math.round(clamp(y2 + dy, y1 + 4, page.height)),
            ];
        return markBlock({ ...block, bbox }, ['bbox']);
      }),
    }));
  }

  function handlePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragState || !currentPage) return;
    const point = canvasPoint(event);
    if (point && dragState.mode === 'draw') {
      const x1 = Math.round(Math.min(dragState.startX, point.x));
      const y1 = Math.round(Math.min(dragState.startY, point.y));
      const x2 = Math.round(Math.max(dragState.startX, point.x));
      const y2 = Math.round(Math.max(dragState.startY, point.y));
      if (x2 - x1 > 8 && y2 - y1 > 8) addBlock([x1, y1, x2, y2]);
    }
    setDragState(null);
  }

  function undo() {
    if (historyPointer <= 0 || !payload) return;
    const nextPointer = historyPointer - 1;
    setHistoryPointer(nextPointer);
    setPayload({ ...payload, pages: history[nextPointer] });
  }

  function redo() {
    if (historyPointer >= history.length - 1 || !payload) return;
    const nextPointer = historyPointer + 1;
    setHistoryPointer(nextPointer);
    setPayload({ ...payload, pages: history[nextPointer] });
  }

  async function save(mode: 'draft' | 'submit' | 'overwrite') {
    if (!payload) return;
    if (mode === 'overwrite' && !window.confirm('该操作将覆盖原始 Completed 标注结果，是否继续？')) return;
    const path = mode === 'draft'
      ? `/api/datasets/${datasetId}/annotations/second/draft`
      : mode === 'overwrite'
        ? `/api/datasets/${datasetId}/annotations/overwrite`
        : `/api/datasets/${datasetId}/annotations/second/submit`;
    try {
      setError('');
      await fetchJson(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pages: payload.pages }),
      });
      setMessage(mode === 'draft' ? '草稿已保存' : mode === 'overwrite' ? '已覆盖保存' : '二次标注版本已提交');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message.includes('404') ? '保存接口不存在或后端仍是旧版本，请重启后端后再保存二次标注。' : message);
    }
  }

  const pageOptions = useMemo(() => pages.map((page, index) => ({ page, index })), [pages]);

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[#101112] text-white">
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/10 bg-[#0c0d0e] px-6">
        <div className="flex items-center gap-4">
          <button onClick={onGoBack} className="p-2 text-white/70 hover:bg-white/10 hover:text-white" aria-label="Back">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-sm font-semibold">{payload?.filename || datasetId}</h1>
            <p className="text-[11px] text-white/45">二次人工标注校验 · {payload?.active_version || 'loading'}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ToolbarButton icon={<Save className="h-4 w-4" />} label="保存草稿" onClick={() => save('draft')} />
          <ToolbarButton icon={<Copy className="h-4 w-4" />} label="另存为二次版本" onClick={() => save('submit')} primary />
          <ToolbarButton icon={<Check className="h-4 w-4" />} label="覆盖保存" onClick={() => save('overwrite')} danger />
          <ToolbarButton icon={<Undo2 className="h-4 w-4" />} label="撤销" onClick={undo} disabled={historyPointer <= 0} />
          <ToolbarButton icon={<Redo2 className="h-4 w-4" />} label="重做" onClick={redo} disabled={historyPointer >= history.length - 1} />
          <ToolbarButton icon={<HelpCircle className="h-4 w-4" />} label="快捷键" onClick={() => alert('拖拽空白区域添加选框；拖拽选框移动；拖拽右下角调整大小；右侧面板修改 label 和文本。')} />
        </div>
      </header>

      {(message || error) && (
        <div className={`border-b px-6 py-2 text-xs ${error ? 'border-rose-400/30 bg-rose-500/10 text-rose-100' : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100'}`}>
          {error || message}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className="w-64 shrink-0 overflow-y-auto border-r border-white/10 bg-[#0c0d0e] p-4">
          <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/45">页面列表</h2>
          <div className="space-y-2">
            {pageOptions.map(({ page, index }) => (
              <button
                key={page.page_id}
                onClick={() => {
                  setCurrentPageIndex(index);
                  setSelectedBlockId(page.blocks[0]?.id || null);
                }}
                className={`flex w-full items-center gap-3 border p-2 text-left ${index === currentPageIndex ? 'border-white/35 bg-white/10' : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.06]'}`}
              >
                <div className="h-14 w-10 shrink-0 bg-white/10 bg-cover bg-center" style={{ backgroundImage: `url(${page.image_url})` }} />
                <div className="min-w-0">
                  <p className="text-xs font-semibold">Page {page.page_id + 1}</p>
                  <p className="text-[10px] text-white/45">{page.blocks.length} blocks</p>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col bg-[#151617]">
          <div className="absolute left-4 top-4 z-20 flex items-center gap-2 border border-white/10 bg-black/55 px-3 py-2 text-xs text-white/70">
            <MousePointer2 className="h-4 w-4" />
            <span>拖拽空白添加，拖拽框移动，右下角缩放</span>
          </div>

          <div className="flex flex-1 items-center justify-center overflow-auto p-12">
            {currentPage ? (
              <div
                ref={canvasRef}
                onPointerDown={handleCanvasPointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                className="relative shrink-0 bg-white bg-cover bg-center shadow-2xl"
                style={{
                  width: canvasWidth,
                  height: canvasHeight,
                  transform: `scale(${scale})`,
                  transformOrigin: 'center',
                  backgroundImage: `url(${currentPage.image_url})`,
                }}
              >
                {currentPage.blocks.map((block) => {
                  const [x1, y1, x2, y2] = block.bbox;
                  const left = (x1 / Math.max(currentPage.width, 1)) * 100;
                  const top = (y1 / Math.max(currentPage.height, 1)) * 100;
                  const width = ((x2 - x1) / Math.max(currentPage.width, 1)) * 100;
                  const height = ((y2 - y1) / Math.max(currentPage.height, 1)) * 100;
                  const selected = block.id === selectedBlockId;
                  return (
                    <div
                      key={block.id}
                      onPointerDown={(event) => handleBlockPointerDown(event, block, 'move')}
                      className={`absolute cursor-move border-2 ${selected ? 'border-cyan-300 bg-cyan-300/15 shadow-[0_0_0_2px_rgba(34,211,238,0.25)]' : 'border-amber-300 bg-amber-300/10'}`}
                      style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
                    >
                      <span className="absolute -top-5 left-0 bg-black/80 px-1.5 py-0.5 text-[10px] text-white">{block.level ? `${block.level} · ` : ''}{block.label}</span>
                      <button
                        type="button"
                        onPointerDown={(event) => handleBlockPointerDown(event, block, 'resize')}
                        className="absolute bottom-0 right-0 h-3 w-3 translate-x-1/2 translate-y-1/2 cursor-se-resize bg-cyan-300"
                        aria-label="Resize block"
                      />
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-white/45">正在加载标注数据...</div>
            )}
          </div>

          <div className="absolute bottom-6 left-1/2 flex -translate-x-1/2 items-center gap-2 border border-white/10 bg-black/70 px-4 py-2">
            <button onClick={() => setScale((value) => Math.max(0.35, value - 0.1))} className="p-2 text-white/70 hover:bg-white/10"><ZoomOut className="h-4 w-4" /></button>
            <span className="w-12 text-center text-xs">{Math.round(scale * 100)}%</span>
            <button onClick={() => setScale((value) => Math.min(1.8, value + 0.1))} className="p-2 text-white/70 hover:bg-white/10"><ZoomIn className="h-4 w-4" /></button>
            <button onClick={() => setScale(0.78)} className="p-2 text-white/70 hover:bg-white/10"><Maximize2 className="h-4 w-4" /></button>
          </div>
        </main>

        <aside className="w-80 shrink-0 overflow-y-auto border-l border-white/10 bg-[#0c0d0e] p-4">
          <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/45">选框属性</h2>
          {selectedBlock ? (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-white/45">Label</label>
                <select
                  value={selectedBlock.label}
                  onChange={(event) => updateSelectedBlock({ label: event.target.value, block_type: event.target.value }, ['label'])}
                  className="w-full border border-white/10 bg-[#151617] px-3 py-2 text-sm text-white outline-none focus:border-white/35"
                >
                  {labelTypes.map((label) => <option key={label} value={label}>{label}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-white/45">Heading Level</label>
                <select
                  value={selectedBlock.level || ''}
                  onChange={(event) => updateSelectedBlock({ level: (event.target.value || null) as AnnotationBlock['level'] }, ['level'])}
                  className="w-full border border-white/10 bg-[#151617] px-3 py-2 text-sm text-white outline-none focus:border-white/35"
                >
                  <option value="">None</option>
                  <option value="H1">H1</option>
                  <option value="H2">H2</option>
                  <option value="H3">H3</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-white/45">Text</label>
                <textarea
                  value={selectedBlock.text}
                  onChange={(event) => updateSelectedBlock({ text: event.target.value }, ['text'])}
                  rows={8}
                  className="w-full resize-none border border-white/10 bg-[#151617] px-3 py-2 text-sm text-white outline-none focus:border-white/35"
                />
              </div>
              <div className="border border-white/10 bg-white/[0.03] p-3 text-[11px] text-white/55">
                <p>ID: {selectedBlock.id}</p>
                <p>BBox: [{selectedBlock.bbox.join(', ')}]</p>
                <p>Level: {selectedBlock.level || 'None'}</p>
                <p>Source: {selectedBlock.source || 'model'}</p>
                <p>Modified: {selectedBlock.modified ? 'yes' : 'no'}</p>
              </div>
              <button onClick={deleteSelectedBlock} className="flex w-full items-center justify-center gap-2 border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-100 hover:bg-rose-500/20">
                <Trash2 className="h-4 w-4" />
                删除选框
              </button>
            </div>
          ) : (
            <div className="rounded border border-white/10 bg-white/[0.03] p-4 text-sm text-white/45">
              <Plus className="mb-2 h-5 w-5" />
              选择一个选框，或在画布空白处拖拽新增选框。
            </div>
          )}
          <div className="mt-6">
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-white/45">当前页选框</h3>
            <div className="space-y-2">
              {currentPage?.blocks.map((block) => (
                <button
                  key={block.id}
                  onClick={() => setSelectedBlockId(block.id)}
                  className={`w-full border p-2 text-left text-xs ${block.id === selectedBlockId ? 'border-cyan-300/50 bg-cyan-300/10' : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.06]'}`}
                >
                  <p className="font-semibold text-white">{block.level ? `${block.level} · ` : ''}{block.label}</p>
                  <p className="truncate text-white/45">{block.text || block.id}</p>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function ToolbarButton({ icon, label, onClick, primary, danger, disabled }: { icon: React.ReactNode; label: string; onClick: () => void; primary?: boolean; danger?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-2 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
        primary ? 'bg-white text-black hover:bg-white/90' : danger ? 'border border-rose-400/30 text-rose-100 hover:bg-rose-500/10' : 'border border-white/10 text-white/75 hover:bg-white/10 hover:text-white'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
