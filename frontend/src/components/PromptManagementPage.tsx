import React, { useEffect, useMemo, useState } from 'react';
import {
  Copy,
  Eye,
  FileText,
  Maximize2,
  PauseCircle,
  PlayCircle,
  Plus,
  RotateCcw,
  Save,
  Search,
  Star,
  TestTube2,
  Trash2,
  X,
} from 'lucide-react';
import { PromptRecord, PromptTaskType, PromptTestResult, PromptType } from '../types';

const PROMPT_TYPES: Array<{ id: PromptType; label: string }> = [
  { id: 'data_annotation', label: '数据标注提示词' },
  { id: 'second_review', label: '二次校验提示词' },
  { id: 'data_cleaning', label: '数据清洗提示词' },
  { id: 'data_conversion', label: '数据转换提示词' },
  { id: 'model_inference', label: '模型推理提示词' },
  { id: 'system_role', label: '系统角色提示词' },
  { id: 'custom', label: '自定义提示词' },
];

const PROMPT_TASKS: Array<{ id: PromptTaskType; label: string }> = [
  { id: 'layout_analysis', label: '文档版面分析' },
  { id: 'table_recognition', label: '表格识别' },
  { id: 'image_captioning', label: '图像描述生成' },
  { id: 'data_quality_check', label: '数据质量校验' },
  { id: 'llamafactory_conversion', label: 'LLaMA-Factory 格式转换' },
  { id: 'swift_conversion', label: 'SWIFT 格式转换' },
  { id: 'second_manual_review', label: '二次人工校验' },
  { id: 'auto_annotation', label: '自动标注' },
  { id: 'custom', label: '其他自定义任务' },
];

type PanelMode = 'view' | 'edit' | 'create';

const EMPTY_PROMPT: PromptRecord = {
  id: '',
  name: '',
  description: '',
  type: 'data_annotation',
  task_type: 'layout_analysis',
  model_name: 'all',
  content: '',
  variables: '{{input_text}}\n{{image_path}}\n{{ocr_result}}\n{{previous_context}}\n{{label_schema}}\n{{dataset_info}}\n{{model_output}}',
  default_values: {},
  version: 'v1.0',
  status: 'enabled',
  is_default: false,
  notes: '',
  usage_scenarios: [],
  versions: [],
};

export default function PromptManagementPage() {
  const [prompts, setPrompts] = useState<PromptRecord[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [mode, setMode] = useState<PanelMode>('view');
  const [draft, setDraft] = useState<PromptRecord>(EMPTY_PROMPT);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | PromptType>('all');
  const [taskFilter, setTaskFilter] = useState<'all' | PromptTaskType>('all');
  const [modelFilter, setModelFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'enabled' | 'disabled'>('all');
  const [defaultFilter, setDefaultFilter] = useState<'all' | 'true' | 'false'>('all');
  const [sortBy, setSortBy] = useState<'created_at' | 'updated_at' | 'name'>('updated_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [fullScreenEditor, setFullScreenEditor] = useState(false);
  const [testInputs, setTestInputs] = useState('{\n  "input_text": "这里是一段测试文本",\n  "ocr_result": "",\n  "label_schema": "doc_title, paragraph_title, text, table_of_contents, table, formula, chart, flowchart, image, caption, vision_footnote, header, footer, handwriting, seal"\n}');
  const [callModel, setCallModel] = useState(false);
  const [testResult, setTestResult] = useState<PromptTestResult | null>(null);

  const selectedPrompt = useMemo(() => prompts.find((item) => item.id === selectedId) || prompts[0], [prompts, selectedId]);
  const models = useMemo(() => ['all', ...Array.from(new Set(prompts.map((item) => item.model_name).filter(Boolean)))], [prompts]);

  useEffect(() => {
    loadPrompts();
  }, [search, typeFilter, taskFilter, modelFilter, statusFilter, defaultFilter, sortBy, sortOrder]);

  useEffect(() => {
    if (!selectedPrompt) return;
    setSelectedId(selectedPrompt.id);
    if (mode === 'view') setDraft(selectedPrompt);
  }, [selectedPrompt?.id]);

  async function loadPrompts() {
    try {
      setError('');
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (typeFilter !== 'all') params.set('type', typeFilter);
      if (taskFilter !== 'all') params.set('task_type', taskFilter);
      if (modelFilter !== 'all') params.set('model_name', modelFilter);
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (defaultFilter !== 'all') params.set('is_default', defaultFilter);
      params.set('sort_by', sortBy);
      params.set('sort_order', sortOrder);
      const payload = await fetchJson<{ prompts: PromptRecord[] }>(`/api/prompts?${params.toString()}`);
      setPrompts(payload.prompts || []);
      if (!selectedId && payload.prompts?.[0]) setSelectedId(payload.prompts[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function openCreate() {
    setMode('create');
    setDraft({ ...EMPTY_PROMPT, id: `prompt_${Date.now()}` });
    setTestResult(null);
  }

  function openEdit(prompt: PromptRecord) {
    setSelectedId(prompt.id);
    setDraft(prompt);
    setMode('edit');
    setTestResult(null);
  }

  async function savePrompt() {
    try {
      setError('');
      const body = normalizeDraftForSave(draft);
      const payload = mode === 'create'
        ? await fetchJson<{ prompt: PromptRecord }>('/api/prompts', { method: 'POST', body: JSON.stringify(body) })
        : await fetchJson<{ prompt: PromptRecord }>(`/api/prompts/${draft.id}`, { method: 'PUT', body: JSON.stringify(body) });
      setMessage('提示词已保存');
      setMode('view');
      setSelectedId(payload.prompt.id);
      await loadPrompts();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function runAction(prompt: PromptRecord, action: 'copy' | 'enable' | 'disable' | 'set-default') {
    try {
      setError('');
      if (action === 'disable' && prompt.is_default) {
        setError('默认提示词不能直接停用，请先指定新的默认提示词。');
        return;
      }
      const payload = await fetchJson<{ prompt: PromptRecord }>(`/api/prompts/${prompt.id}/${action}`, { method: 'POST', body: '{}' });
      setMessage(actionText(action));
      setSelectedId(payload.prompt.id);
      await loadPrompts();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function deletePrompt(prompt: PromptRecord) {
    if (!window.confirm('确认删除该提示词吗？删除后将无法在新任务中使用，但历史任务记录仍会保留。')) return;
    try {
      await fetchJson<{ prompt: PromptRecord }>(`/api/prompts/${prompt.id}`, { method: 'DELETE' });
      setMessage('提示词已删除');
      setSelectedId('');
      await loadPrompts();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function rollback(version: string) {
    if (!selectedPrompt) return;
    if (!window.confirm(`确认恢复到 ${version} 吗？恢复会生成一个新的当前版本。`)) return;
    try {
      await fetchJson<{ prompt: PromptRecord }>(`/api/prompts/${selectedPrompt.id}/rollback`, {
        method: 'POST',
        body: JSON.stringify({ version }),
      });
      setMessage('历史版本已恢复');
      await loadPrompts();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function testPrompt() {
    const target = mode === 'create' ? draft : selectedPrompt;
    if (!target?.id || mode === 'create') {
      setError('请先保存提示词后再测试运行。');
      return;
    }
    try {
      setError('');
      const inputs = JSON.parse(testInputs || '{}');
      const result = await fetchJson<PromptTestResult>(`/api/prompts/${target.id}/test`, {
        method: 'POST',
        body: JSON.stringify({ inputs, call_model: callModel }),
      });
      setTestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section className="flex min-h-[calc(100vh-4rem)] w-full overflow-hidden bg-surface-container-low text-on-surface">
      <aside className="hidden w-72 shrink-0 border-r border-outline-variant/40 bg-surface-container-lowest p-6 lg:block">
        <div className="mb-8">
          <span className="text-label-sm font-bold uppercase tracking-[0.24em] text-on-surface-variant">Prompt Center</span>
          <h1 className="mt-3 text-headline-md font-semibold text-primary">提示词管理</h1>
        </div>
        <button onClick={openCreate} className="mb-6 flex w-full items-center justify-center gap-2 rounded bg-primary px-4 py-3 text-label-md font-bold text-on-primary">
          <Plus className="h-4 w-4" />
          新增提示词
        </button>
        <div className="space-y-2">
          <CategoryButton label="全部提示词" active={typeFilter === 'all'} onClick={() => setTypeFilter('all')} />
          {PROMPT_TYPES.map((type) => (
            <React.Fragment key={type.id}>
              <CategoryButton label={type.label} active={typeFilter === type.id} onClick={() => setTypeFilter(type.id)} />
            </React.Fragment>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="border-b border-outline-variant/40 bg-surface/80 px-6 py-5 backdrop-blur">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <span className="text-label-sm font-bold uppercase tracking-[0.24em] text-on-surface-variant">Manage reusable prompts</span>
              <h2 className="mt-2 text-headline-md font-semibold text-primary">统一管理不同任务、模型和流程使用的 Prompt</h2>
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-7">
              <FilterInput icon={<Search className="h-4 w-4" />} value={search} onChange={setSearch} placeholder="搜索名称/内容" />
              <FilterSelect value={taskFilter} onChange={(value) => setTaskFilter(value as 'all' | PromptTaskType)} options={[{ id: 'all', label: '全部任务' }, ...PROMPT_TASKS]} />
              <FilterSelect value={modelFilter} onChange={setModelFilter} options={models.map((model) => ({ id: model, label: model === 'all' ? '全部模型' : model }))} />
              <FilterSelect value={statusFilter} onChange={(value) => setStatusFilter(value as 'all' | 'enabled' | 'disabled')} options={[{ id: 'all', label: '全部状态' }, { id: 'enabled', label: '启用' }, { id: 'disabled', label: '停用' }]} />
              <FilterSelect value={defaultFilter} onChange={(value) => setDefaultFilter(value as 'all' | 'true' | 'false')} options={[{ id: 'all', label: '默认不限' }, { id: 'true', label: '默认' }, { id: 'false', label: '非默认' }]} />
              <FilterSelect value={sortBy} onChange={(value) => setSortBy(value as 'created_at' | 'updated_at' | 'name')} options={[{ id: 'updated_at', label: '按更新时间' }, { id: 'created_at', label: '按创建时间' }, { id: 'name', label: '按名称' }]} />
              <FilterSelect value={sortOrder} onChange={(value) => setSortOrder(value as 'asc' | 'desc')} options={[{ id: 'desc', label: '倒序' }, { id: 'asc', label: '正序' }]} />
            </div>
          </div>
          {(message || error) && (
            <div className={`mt-4 rounded border px-4 py-3 text-label-md font-semibold ${error ? 'border-error/20 bg-error/10 text-error' : 'border-primary/20 bg-primary/10 text-primary'}`}>
              {error || message}
            </div>
          )}
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1fr)_520px]">
          <div className="overflow-auto p-6">
            <PromptTable
              prompts={prompts}
              selectedId={selectedPrompt?.id}
              onSelect={(prompt) => { setSelectedId(prompt.id); setDraft(prompt); setMode('view'); }}
              onEdit={openEdit}
              onDelete={deletePrompt}
              onAction={runAction}
              onTest={(prompt) => { setSelectedId(prompt.id); setDraft(prompt); setMode('view'); setTimeout(testPrompt, 0); }}
            />
          </div>
          <PromptPanel
            mode={mode}
            draft={draft}
            prompt={selectedPrompt}
            onDraftChange={setDraft}
            onModeChange={setMode}
            onSave={savePrompt}
            onEdit={() => selectedPrompt && openEdit(selectedPrompt)}
            onRollback={rollback}
            testInputs={testInputs}
            onTestInputsChange={setTestInputs}
            callModel={callModel}
            onCallModelChange={setCallModel}
            onTest={testPrompt}
            testResult={testResult}
            onFullScreen={() => setFullScreenEditor(true)}
          />
        </div>
      </div>

      {fullScreenEditor && (
        <div className="fixed inset-0 z-50 bg-black/30 p-6 backdrop-blur">
          <div className="flex h-full flex-col rounded-[1.5rem] border border-outline-variant/60 bg-surface-container-lowest p-5 text-on-surface shadow-[0_24px_80px_rgba(0,0,0,0.12)]">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-headline-sm font-semibold">全屏编辑 Prompt</h3>
              <button onClick={() => setFullScreenEditor(false)} className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container"><X className="h-5 w-5" /></button>
            </div>
            <CodeEditor value={draft.content} onChange={(content) => setDraft({ ...draft, content })} className="min-h-0 flex-1" />
          </div>
        </div>
      )}
    </section>
  );
}

function PromptTable({
  prompts,
  selectedId,
  onSelect,
  onEdit,
  onDelete,
  onAction,
  onTest,
}: {
  prompts: PromptRecord[];
  selectedId?: string;
  onSelect: (prompt: PromptRecord) => void;
  onEdit: (prompt: PromptRecord) => void;
  onDelete: (prompt: PromptRecord) => void;
  onAction: (prompt: PromptRecord, action: 'copy' | 'enable' | 'disable' | 'set-default') => void;
  onTest: (prompt: PromptRecord) => void;
}) {
  return (
    <div className="overflow-hidden rounded border border-outline-variant/40 bg-surface-container-lowest">
      <table className="w-full min-w-[1080px] border-collapse text-left text-label-md">
        <thead className="bg-surface-container text-on-surface-variant">
          <tr>
            {['名称', '描述', '类型', '适用任务', '模型', '版本', '默认', '状态', '创建时间', '更新时间', '操作'].map((head) => (
              <th key={head} className="border-b border-outline-variant/40 px-4 py-3 font-bold">{head}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {prompts.map((prompt) => (
            <tr key={prompt.id} onClick={() => onSelect(prompt)} className={`cursor-pointer border-b border-outline-variant/30 hover:bg-surface-container ${selectedId === prompt.id ? 'bg-primary/5' : ''}`}>
              <td className="px-4 py-3 font-semibold text-primary">{prompt.name}</td>
              <td className="max-w-[220px] truncate px-4 py-3 text-on-surface-variant">{prompt.description || '-'}</td>
              <td className="px-4 py-3">{typeLabel(prompt.type)}</td>
              <td className="px-4 py-3">{taskLabel(prompt.task_type)}</td>
              <td className="px-4 py-3">{prompt.model_name || 'all'}</td>
              <td className="px-4 py-3 font-mono">{prompt.version}</td>
              <td className="px-4 py-3">{prompt.is_default ? <span className="text-primary">默认</span> : '-'}</td>
              <td className="px-4 py-3">{prompt.status === 'enabled' ? '启用' : '停用'}</td>
              <td className="px-4 py-3 text-on-surface-variant">{formatDate(prompt.created_at)}</td>
              <td className="px-4 py-3 text-on-surface-variant">{formatDate(prompt.updated_at)}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1" onClick={(event) => event.stopPropagation()}>
                  <IconButton title="查看" onClick={() => onSelect(prompt)} icon={<Eye className="h-3.5 w-3.5" />} />
                  <IconButton title="编辑" onClick={() => onEdit(prompt)} icon={<FileText className="h-3.5 w-3.5" />} />
                  <IconButton title="复制" onClick={() => onAction(prompt, 'copy')} icon={<Copy className="h-3.5 w-3.5" />} />
                  <IconButton title="测试" onClick={() => onTest(prompt)} icon={<TestTube2 className="h-3.5 w-3.5" />} />
                  <IconButton title={prompt.status === 'enabled' ? '停用' : '启用'} onClick={() => onAction(prompt, prompt.status === 'enabled' ? 'disable' : 'enable')} icon={prompt.status === 'enabled' ? <PauseCircle className="h-3.5 w-3.5" /> : <PlayCircle className="h-3.5 w-3.5" />} />
                  <IconButton title="设为默认" onClick={() => onAction(prompt, 'set-default')} icon={<Star className="h-3.5 w-3.5" />} />
                  <IconButton title="删除" onClick={() => onDelete(prompt)} icon={<Trash2 className="h-3.5 w-3.5" />} />
                </div>
              </td>
            </tr>
          ))}
          {!prompts.length && (
            <tr>
              <td colSpan={11} className="px-4 py-12 text-center text-on-surface-variant">暂无提示词，请点击新增提示词。</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function PromptPanel({
  mode,
  draft,
  prompt,
  onDraftChange,
  onModeChange,
  onSave,
  onEdit,
  onRollback,
  testInputs,
  onTestInputsChange,
  callModel,
  onCallModelChange,
  onTest,
  testResult,
  onFullScreen,
}: {
  mode: PanelMode;
  draft: PromptRecord;
  prompt?: PromptRecord;
  onDraftChange: (prompt: PromptRecord) => void;
  onModeChange: (mode: PanelMode) => void;
  onSave: () => void;
  onEdit: () => void;
  onRollback: (version: string) => void;
  testInputs: string;
  onTestInputsChange: (value: string) => void;
  callModel: boolean;
  onCallModelChange: (value: boolean) => void;
  onTest: () => void;
  testResult: PromptTestResult | null;
  onFullScreen: () => void;
}) {
  const editing = mode === 'edit' || mode === 'create';
  const target = editing ? draft : prompt;
  const contentLineCount = target?.content ? target.content.split('\n').length : 0;
  const contentCharCount = target?.content?.length || 0;
  return (
    <aside className="min-h-0 overflow-auto border-l border-outline-variant/40 bg-surface-container-lowest p-6">
      {!target ? (
        <div className="flex h-full items-center justify-center text-center text-on-surface-variant">请选择或新增一个提示词。</div>
      ) : (
        <div className="space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <span className="text-label-sm font-bold uppercase tracking-[0.24em] text-on-surface-variant">{editing ? 'Edit Prompt' : 'Prompt Detail'}</span>
              <h3 className="mt-2 text-headline-sm font-semibold text-primary">{target.name || '未命名提示词'}</h3>
            </div>
            <div className="flex gap-2">
              {editing ? (
                <button onClick={onSave} className="flex items-center gap-2 rounded bg-primary px-4 py-2 text-label-md font-bold text-on-primary"><Save className="h-4 w-4" />保存</button>
              ) : (
                <button onClick={onEdit} className="rounded border border-outline-variant/50 px-4 py-2 text-label-md font-semibold text-primary">编辑</button>
              )}
              {editing && <button onClick={() => onModeChange('view')} className="rounded border border-outline-variant/50 px-4 py-2 text-label-md font-semibold">取消</button>}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="提示词名称" value={draft.name} disabled={!editing} onChange={(value) => onDraftChange({ ...draft, name: value })} />
            <Field label="适用模型" value={draft.model_name} disabled={!editing} onChange={(value) => onDraftChange({ ...draft, model_name: value || 'all' })} />
            <SelectField label="提示词类型" value={draft.type} disabled={!editing} options={PROMPT_TYPES} onChange={(value) => onDraftChange({ ...draft, type: value as PromptType })} />
            <SelectField label="适用任务" value={draft.task_type} disabled={!editing} options={PROMPT_TASKS} onChange={(value) => onDraftChange({ ...draft, task_type: value as PromptTaskType })} />
          </div>
          <Field label="提示词描述" value={draft.description} disabled={!editing} onChange={(value) => onDraftChange({ ...draft, description: value })} />

          {editing ? (
            <>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-label-sm font-bold uppercase tracking-wider text-on-surface-variant">Prompt 内容</label>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => navigator.clipboard.writeText(draft.content)} className="rounded border border-outline-variant/50 px-2 py-1 text-label-sm">复制</button>
                    <button type="button" onClick={() => formatDraftContent(draft, onDraftChange)} className="rounded border border-outline-variant/50 px-2 py-1 text-label-sm">格式化</button>
                    <button type="button" onClick={onFullScreen} className="rounded border border-outline-variant/50 px-2 py-1 text-label-sm"><Maximize2 className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
                <CodeEditor value={draft.content} onChange={(value) => onDraftChange({ ...draft, content: value })} />
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <TextareaField label="变量参数说明" value={stringifyLoose(draft.variables)} disabled={false} onChange={(value) => onDraftChange({ ...draft, variables: value })} />
                <TextareaField label="默认变量值 JSON" value={JSON.stringify(draft.default_values || {}, null, 2)} disabled={false} onChange={(value) => onDraftChange({ ...draft, default_values: parseJsonObject(value) })} />
              </div>
              <TextareaField label="备注" value={draft.notes || ''} disabled={false} onChange={(value) => onDraftChange({ ...draft, notes: value })} />
            </>
          ) : (
            <section className="rounded-[0.75rem] border border-outline-variant/40 bg-surface-container p-4">
              <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
                <div>
                  <h4 className="text-label-md font-bold text-primary">Prompt 内容</h4>
                  <p className="mt-1 text-label-md text-on-surface-variant">
                    当前内容已收起，共 {contentLineCount} 行、{contentCharCount} 个字符。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => navigator.clipboard.writeText(target.content || '')} className="rounded-[0.75rem] border border-outline-variant/50 px-3 py-2 text-label-md font-semibold text-primary hover:bg-surface-container-high">复制</button>
                  <button type="button" onClick={onEdit} className="rounded-[0.75rem] bg-primary px-4 py-2 text-label-md font-semibold text-on-primary hover:bg-primary/90">编辑提示词</button>
                </div>
              </div>
            </section>
          )}

          <div className="flex flex-wrap gap-4 border-y border-outline-variant/40 py-4 text-label-md">
            <label className="flex items-center gap-2"><input type="checkbox" checked={draft.status === 'enabled'} disabled={!editing} onChange={(event) => onDraftChange({ ...draft, status: event.target.checked ? 'enabled' : 'disabled', is_default: event.target.checked ? draft.is_default : false })} />启用</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={draft.is_default} disabled={!editing || draft.status !== 'enabled'} onChange={(event) => onDraftChange({ ...draft, is_default: event.target.checked })} />设为默认</label>
            <span>当前版本：<b>{target.version}</b></span>
            <span>更新时间：{formatDate(target.updated_at)}</span>
          </div>

          <section>
            <h4 className="mb-3 text-label-md font-bold text-primary">历史版本</h4>
            <div className="max-h-44 space-y-2 overflow-auto">
              {(target.versions || []).slice().reverse().map((version) => (
                <div key={version.id} className="flex items-center justify-between rounded border border-outline-variant/40 px-3 py-2 text-label-sm">
                  <span>{version.version} · {version.change_log || '无修改说明'} · {formatDate(version.created_at)}</span>
                  <button onClick={() => onRollback(version.version)} className="flex items-center gap-1 text-primary"><RotateCcw className="h-3.5 w-3.5" />恢复</button>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h4 className="text-label-md font-bold text-primary">测试运行</h4>
            <TextareaField label="测试输入 JSON" value={testInputs} disabled={false} onChange={onTestInputsChange} />
            <label className="flex items-center gap-2 text-label-md"><input type="checkbox" checked={callModel} onChange={(event) => onCallModelChange(event.target.checked)} />调用模型</label>
            <button onClick={onTest} className="flex items-center gap-2 rounded bg-primary px-4 py-2 text-label-md font-bold text-on-primary"><TestTube2 className="h-4 w-4" />测试运行</button>
            {testResult && (
              <div className="space-y-2 rounded border border-outline-variant/40 bg-surface-container p-3 text-label-sm">
                <p>状态：{testResult.success ? '成功' : '失败'} · 模型：{testResult.model_name || '-'} · 耗时：{testResult.elapsed_ms}ms</p>
                {testResult.error && <p className="text-error">错误：{testResult.error}</p>}
                <pre className="max-h-44 overflow-auto whitespace-pre-wrap rounded bg-surface-container-lowest p-3 font-mono text-on-surface">{testResult.rendered_prompt}</pre>
                <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-surface-container-high p-3">{testResult.model_output}</pre>
              </div>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}

function CodeEditor({ value, onChange, disabled = false, className = '' }: { value: string; onChange: (value: string) => void; disabled?: boolean; className?: string }) {
  const lineCount = Math.max(1, value.split('\n').length);
  return (
    <div className={`flex min-h-[280px] overflow-hidden rounded border border-outline-variant/50 bg-surface-container-lowest text-on-surface ${className}`}>
      <div className="select-none border-r border-outline-variant/40 bg-surface-container px-3 py-3 text-right font-mono text-xs leading-6 text-on-surface-variant">
        {Array.from({ length: lineCount }, (_, index) => <div key={index}>{index + 1}</div>)}
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        wrap="soft"
        spellCheck={false}
        className="min-h-full flex-1 resize-none bg-transparent p-3 font-mono text-xs leading-6 text-on-surface outline-none disabled:text-on-surface-variant"
      />
    </div>
  );
}

function Field({ label, value, disabled, onChange }: { label: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return (
    <label className="block text-label-sm font-semibold text-on-surface-variant">
      {label}
      <input value={value || ''} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border border-outline-variant/50 bg-surface-container px-3 py-2 text-label-md text-on-surface outline-none disabled:opacity-70" />
    </label>
  );
}

function TextareaField({ label, value, disabled, onChange }: { label: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return (
    <label className="block text-label-sm font-semibold text-on-surface-variant">
      {label}
      <textarea value={value || ''} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="mt-1 min-h-24 w-full resize-y rounded border border-outline-variant/50 bg-surface-container px-3 py-2 font-mono text-xs text-on-surface outline-none disabled:opacity-70" />
    </label>
  );
}

function SelectField({ label, value, disabled, options, onChange }: { label: string; value: string; disabled: boolean; options: Array<{ id: string; label: string }>; onChange: (value: string) => void }) {
  return (
    <label className="block text-label-sm font-semibold text-on-surface-variant">
      {label}
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border border-outline-variant/50 bg-surface-container px-3 py-2 text-label-md text-on-surface outline-none disabled:opacity-70">
        {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select>
    </label>
  );
}

function CategoryButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return <button onClick={onClick} className={`w-full rounded px-3 py-2 text-left text-label-md font-semibold ${active ? 'bg-primary text-on-primary' : 'text-on-surface-variant hover:bg-surface-container'}`}>{label}</button>;
}

function FilterInput({ icon, value, onChange, placeholder }: { icon: React.ReactNode; value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="flex items-center gap-2 rounded border border-outline-variant/50 bg-surface-container-lowest px-3 py-2">
      {icon}
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="min-w-0 flex-1 bg-transparent text-label-md outline-none" />
    </label>
  );
}

function FilterSelect({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: Array<{ id: string; label: string }> }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} className="rounded border border-outline-variant/50 bg-surface-container-lowest px-3 py-2 text-label-md outline-none">
      {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
    </select>
  );
}

function IconButton({ title, onClick, icon }: { title: string; onClick: () => void; icon: React.ReactNode }) {
  return <button type="button" title={title} onClick={onClick} className="rounded border border-outline-variant/40 bg-surface-container px-1.5 py-1 text-on-surface-variant hover:text-primary">{icon}</button>;
}

function normalizeDraftForSave(draft: PromptRecord) {
  return {
    ...draft,
    default_values: draft.default_values || {},
    variables: draft.variables || '',
    change_log: '页面保存',
  };
}

function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  return fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload as T;
  });
}

function formatDraftContent(draft: PromptRecord, onDraftChange: (prompt: PromptRecord) => void) {
  try {
    onDraftChange({ ...draft, content: JSON.stringify(JSON.parse(draft.content), null, 2) });
  } catch {
    onDraftChange({ ...draft, content: draft.content.trim() });
  }
}

function parseJsonObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value || '{}');
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function stringifyLoose(value: PromptRecord['variables']): string {
  return typeof value === 'string' ? value : JSON.stringify(value || {}, null, 2);
}

function typeLabel(type: PromptType) {
  return PROMPT_TYPES.find((item) => item.id === type)?.label || type;
}

function taskLabel(task: PromptTaskType) {
  return PROMPT_TASKS.find((item) => item.id === task)?.label || task;
}

function actionText(action: string) {
  if (action === 'copy') return '提示词已复制';
  if (action === 'enable') return '提示词已启用';
  if (action === 'disable') return '提示词已停用';
  if (action === 'set-default') return '已设置为默认提示词';
  return '操作完成';
}

function formatDate(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN');
}
