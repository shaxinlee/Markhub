import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  ClipboardCheck,
  Copy,
  FileText,
  Filter,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';

type ReviewStatus = 'requires_independent_human_review' | 'in_progress' | 'human_reviewed';
type NullableText = string | null;
type GoldEntity = Record<string, NullableText | string[]>;

interface GoldRule {
  规则类型: NullableText;
  主体: GoldEntity[];
  行为动作: GoldEntity[];
  行为对象: GoldEntity[];
  约束条件: GoldEntity[];
  违规后果: GoldEntity[];
  参照制度: GoldEntity[];
}

interface GoldAnswer {
  制度文件: { 制度名称: NullableText; 制度条款: { 条款原文: NullableText } };
  制度规则: GoldRule[];
}

interface GoldUnit {
  dataset_version: string;
  unit_id: string;
  document_id: string;
  document_name: string;
  source_markdown: string;
  source_sha256: string;
  unit_index: number;
  unit_number: string;
  numbering_style: string;
  context: Array<{ number?: string; title?: string }>;
  source_text: string;
  input_text: string;
  gold_answer: GoldAnswer;
  annotation_status: string;
  review_status: ReviewStatus;
  adjudication_notes: string[];
  reviewed_by?: string;
  reviewed_at?: string;
}

interface UnitSummary {
  unit_id: string;
  document_id: string;
  document_name: string;
  unit_index: number;
  unit_number: string;
  input_preview: string;
  rule_count: number;
  review_status: ReviewStatus;
  valid: boolean;
  error_count: number;
}

interface ValidationIssue {
  severity: 'error' | 'warning';
  code: string;
  path: string;
  message: string;
}

interface ValidationResult {
  valid: boolean;
  error_count: number;
  warning_count: number;
  issues: ValidationIssue[];
}

interface Summary {
  revision: string;
  document_count: number;
  unit_count: number;
  rule_count: number;
  invalid_unit_count: number;
  status_counts: Record<string, number>;
  documents: Array<{ document_id: string; document_name: string; unit_count: number; reviewed_count: number }>;
  vocabularies: Record<string, string[]>;
}

const STATUS_LABELS: Record<ReviewStatus, string> = {
  requires_independent_human_review: '待审查',
  in_progress: '审查中',
  human_reviewed: '已通过',
};

const ENTITY_SECTIONS: Array<{
  key: keyof Pick<GoldRule, '主体' | '行为动作' | '行为对象' | '约束条件' | '违规后果' | '参照制度'>;
  title: string;
  description: string;
  fields: Array<{ key: string; label: string; vocabulary?: string; aliases?: boolean; wide?: boolean }>;
  empty: GoldEntity;
}> = [
  {
    key: '主体', title: '主体', description: '谁适用、负责、执行或审批',
    fields: [
      { key: '主体名称', label: '主体名称', wide: true },
      { key: '主体别名', label: '主体别名', aliases: true },
      { key: '主体角色', label: '主体角色', vocabulary: '主体角色' },
    ],
    empty: { 主体名称: null, 主体别名: [], 主体角色: '其他' },
  },
  {
    key: '行为动作', title: '行为动作', description: '规则要求发生的核心动作',
    fields: [
      { key: '动作名称', label: '动作名称', wide: true },
      { key: '动作类型', label: '动作类型', vocabulary: '动作类型' },
    ],
    empty: { 动作名称: null, 动作类型: '其他' },
  },
  {
    key: '行为对象', title: '行为对象', description: '动作所指向的事项或实体',
    fields: [
      { key: '对象名称', label: '对象名称', wide: true },
      { key: '对象类型', label: '对象类型', vocabulary: '对象类型' },
    ],
    empty: { 对象名称: null, 对象类型: '其他' },
  },
  {
    key: '约束条件', title: '约束条件', description: '时间、金额、前提、审批及例外',
    fields: [
      { key: '约束类型', label: '约束类型', vocabulary: '约束类型' },
      { key: '约束内容', label: '约束内容', wide: true },
      { key: '来源类别', label: '来源类别', vocabulary: '来源类别' },
      { key: '关联事项', label: '关联事项', wide: true },
    ],
    empty: { 约束类型: '其他', 约束内容: null, 来源类别: '适用条件', 关联事项: null },
  },
  {
    key: '违规后果', title: '违规后果', description: '触发后果及相应处理措施',
    fields: [
      { key: '触发条件', label: '触发条件', wide: true },
      { key: '后果类型', label: '后果类型', vocabulary: '后果类型' },
      { key: '处理措施', label: '处理措施', wide: true },
      { key: '处理对象', label: '处理对象' },
      { key: '执行主体', label: '执行主体' },
    ],
    empty: { 触发条件: null, 后果类型: '其他', 处理措施: null, 处理对象: null, 执行主体: null },
  },
  {
    key: '参照制度', title: '参照制度', description: '原文明确引用的法规或内部制度',
    fields: [
      { key: '参照目标', label: '参照目标', wide: true },
      { key: '参照目标类型', label: '目标类型', vocabulary: '参照目标类型' },
      { key: '文号', label: '文号' },
    ],
    empty: { 参照目标: null, 参照目标类型: '其他', 文号: null },
  },
];

const EMPTY_RULE: GoldRule = {
  规则类型: '其他', 主体: [], 行为动作: [], 行为对象: [], 约束条件: [], 违规后果: [], 参照制度: [],
};

export default function GoldReviewWorkspace() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [units, setUnits] = useState<UnitSummary[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [unit, setUnit] = useState<GoldUnit | null>(null);
  const [revision, setRevision] = useState('');
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [documentFilter, setDocumentFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [reviewer, setReviewer] = useState(() => window.localStorage.getItem('markhub-gold-reviewer') || '独立审查员');
  const [reviewNote, setReviewNote] = useState('');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const fetchJson = useCallback(async (url: string, options?: RequestInit) => {
    const response = await fetch(url, { cache: 'no-store', ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }, []);

  const loadSummary = useCallback(async () => {
    const payload = await fetchJson('/api/gold-review/summary');
    setSummary(payload);
  }, [fetchJson]);

  const loadUnits = useCallback(async () => {
    const params = new URLSearchParams();
    if (documentFilter) params.set('document_id', documentFilter);
    if (statusFilter) params.set('review_status', statusFilter);
    if (debouncedQuery) params.set('q', debouncedQuery);
    const payload = await fetchJson(`/api/gold-review/units?${params.toString()}`);
    const nextUnits: UnitSummary[] = payload.units || [];
    setUnits(nextUnits);
    setSelectedId((current) => nextUnits.some((item) => item.unit_id === current) ? current : (nextUnits[0]?.unit_id || ''));
  }, [debouncedQuery, documentFilter, fetchJson, statusFilter]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadSummary(), loadUnits()])
      .catch((error) => setFeedback({ type: 'error', message: `加载失败：${error.message}` }))
      .finally(() => setLoading(false));
  }, [loadSummary, loadUnits]);

  useEffect(() => {
    if (!selectedId) {
      setUnit(null);
      return;
    }
    setDetailLoading(true);
    fetchJson(`/api/gold-review/units/${selectedId}`)
      .then((payload) => {
        setUnit(payload.unit);
        setRevision(payload.revision);
        setValidation(payload.validation);
        setReviewNote('');
        setDirty(false);
      })
      .catch((error) => setFeedback({ type: 'error', message: `读取单元失败：${error.message}` }))
      .finally(() => setDetailLoading(false));
  }, [fetchJson, selectedId]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const setEditedUnit = (next: GoldUnit) => {
    setUnit(next);
    setDirty(true);
    setFeedback(null);
  };

  const validateDraft = useCallback(async (): Promise<ValidationResult | null> => {
    if (!unit) return null;
    setValidating(true);
    try {
      const payload = await fetchJson(`/api/gold-review/units/${unit.unit_id}/validate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ unit }),
      });
      setValidation(payload.validation);
      setFeedback(payload.validation.valid
        ? { type: 'success', message: '严格校验通过：schema、证据值和受控词表均合规。' }
        : { type: 'error', message: `发现 ${payload.validation.error_count} 个严格错误，请按问题清单修正。` });
      return payload.validation;
    } catch (error) {
      setFeedback({ type: 'error', message: `校验失败：${error instanceof Error ? error.message : '未知错误'}` });
      return null;
    } finally {
      setValidating(false);
    }
  }, [fetchJson, unit]);

  const save = useCallback(async (status: ReviewStatus) => {
    if (!unit || saving) return;
    if (status === 'human_reviewed') {
      const checked = await validateDraft();
      if (!checked?.valid) return;
    }
    setSaving(true);
    try {
      const payload = await fetchJson(`/api/gold-review/units/${unit.unit_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_revision: revision,
          gold_answer: unit.gold_answer,
          adjudication_notes: unit.adjudication_notes,
          review_status: status,
          reviewer,
          review_note: reviewNote,
        }),
      });
      setUnit(payload.unit);
      setRevision(payload.revision);
      setValidation(payload.validation);
      setDirty(false);
      setReviewNote('');
      window.localStorage.setItem('markhub-gold-reviewer', reviewer);
      setFeedback({
        type: 'success',
        message: status === 'human_reviewed' ? '已保存并标记为人工审查通过。' : '审查进度已保存，原数据备份已生成。',
      });
      await Promise.all([loadSummary(), loadUnits()]);
    } catch (error) {
      setFeedback({ type: 'error', message: `保存失败：${error instanceof Error ? error.message : '未知错误'}` });
    } finally {
      setSaving(false);
    }
  }, [fetchJson, loadSummary, loadUnits, reviewNote, reviewer, revision, saving, unit, validateDraft]);

  const selectUnit = (unitId: string) => {
    if (unitId === selectedId) return;
    if (dirty && !window.confirm('当前单元有未保存修改，确定离开并丢弃这些修改吗？')) return;
    setSelectedId(unitId);
  };

  const selectedIndex = units.findIndex((item) => item.unit_id === selectedId);
  const move = useCallback((offset: number) => {
    const next = units[selectedIndex + offset];
    if (next) selectUnit(next.unit_id);
  // selectUnit intentionally reads the latest dirty state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIndex, units, dirty]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        void save('in_progress');
      }
      if (event.altKey && event.key === 'ArrowLeft') move(-1);
      if (event.altKey && event.key === 'ArrowRight') move(1);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [move, save]);

  const reviewed = summary?.status_counts.human_reviewed || 0;
  const pending = (summary?.unit_count || 0) - reviewed;

  if (loading) {
    return <div className="flex h-[calc(100dvh-4rem)] w-full items-center justify-center"><Loader2 className="h-7 w-7 animate-spin" aria-label="正在加载金标准" /></div>;
  }

  return (
    <section className="flex h-[calc(100dvh-4rem)] min-h-[640px] w-full flex-col overflow-hidden bg-surface-container-low" aria-labelledby="gold-review-title">
      <div className="shrink-0 border-b border-outline-variant/50 bg-surface-container-lowest px-4 py-3 md:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-label-sm font-bold uppercase tracking-[0.14em] text-on-surface-variant">
              <ShieldCheck className="h-4 w-4" /> Independent review
            </div>
            <h1 id="gold-review-title" className="mt-1 text-headline-md font-bold text-on-surface">金标准审查工作台</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-label-md tabular-nums">
            <Metric label="制度" value={summary?.document_count || 0} />
            <Metric label="单元" value={summary?.unit_count || 0} />
            <Metric label="规则" value={summary?.rule_count || 0} />
            <Metric label="已通过" value={reviewed} tone="success" />
            <Metric label="待处理" value={pending} tone="warning" />
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(220px,38dvh)_minmax(0,1fr)] lg:grid-cols-[310px_minmax(0,1fr)] lg:grid-rows-1">
        <aside className="flex min-h-0 flex-col border-r border-outline-variant/50 bg-surface-container-lowest" aria-label="标注单元列表">
          <div className="space-y-2 border-b border-outline-variant/40 p-3">
            <label className="relative block">
              <span className="sr-only">搜索条款</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} className="h-11 w-full rounded-lg border border-outline-variant bg-surface-container-lowest pl-9 pr-3 text-label-md outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15" placeholder="搜索条号或原文" type="search" />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <FilterSelect label="制度文档" value={documentFilter} onChange={setDocumentFilter}>
                <option value="">全部制度</option>
                {summary?.documents.map((doc) => <option key={doc.document_id} value={doc.document_id}>{doc.document_id} · {doc.document_name}</option>)}
              </FilterSelect>
              <FilterSelect label="审查状态" value={statusFilter} onChange={setStatusFilter}>
                <option value="">全部状态</option>
                {(Object.keys(STATUS_LABELS) as ReviewStatus[]).map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
              </FilterSelect>
            </div>
            <div className="flex items-center justify-between text-label-sm text-on-surface-variant">
              <span>筛选结果 {units.length} 条</span>
              <button type="button" onClick={() => void Promise.all([loadSummary(), loadUnits()])} className="flex h-10 items-center gap-1.5 rounded-lg px-2 font-medium hover:bg-surface-container focus-visible:outline-2 focus-visible:outline-offset-2" aria-label="刷新审查数据"><RefreshCw className="h-4 w-4" />刷新</button>
            </div>
          </div>
          <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-2">
            {units.length ? units.map((item) => (
              <button key={item.unit_id} type="button" onClick={() => selectUnit(item.unit_id)} className={`mb-1.5 w-full rounded-xl border p-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${selectedId === item.unit_id ? 'border-primary bg-primary text-on-primary' : 'border-transparent bg-surface-container-lowest hover:border-outline-variant hover:bg-surface-container-low'}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <StatusIcon status={item.review_status} />
                    <span className="font-mono text-label-sm font-semibold">{item.unit_id}</span>
                  </div>
                  <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${selectedId === item.unit_id ? 'bg-on-primary/15' : 'bg-surface-container-high text-on-surface-variant'}`}>{item.rule_count} 规则</span>
                </div>
                <div className="mt-2 flex items-center gap-2 text-label-sm font-semibold"><span>{item.unit_number}</span><span className="opacity-60">·</span><span>{STATUS_LABELS[item.review_status]}</span></div>
                <p className={`mt-1.5 line-clamp-2 text-xs leading-5 ${selectedId === item.unit_id ? 'text-on-primary/75' : 'text-on-surface-variant'}`}>{item.input_preview}</p>
                {!item.valid && <div className={`mt-2 flex items-center gap-1 text-xs font-semibold ${selectedId === item.unit_id ? 'text-on-primary' : 'text-error'}`}><AlertCircle className="h-3.5 w-3.5" />{item.error_count} 个严格错误</div>}
              </button>
            )) : <EmptyList />}
          </div>
        </aside>

        <main className="min-h-0 overflow-hidden" aria-label="金标准编辑区">
          {detailLoading ? (
            <div className="flex h-full items-center justify-center"><Loader2 className="h-7 w-7 animate-spin" aria-label="正在读取单元" /></div>
          ) : unit ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-outline-variant/50 bg-surface px-4 py-2 md:px-5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-label-sm font-bold text-on-surface-variant">{unit.unit_id}</span>
                    <span className="text-label-md font-bold">{unit.unit_number}</span>
                    <StatusBadge status={unit.review_status} />
                    {dirty && <span className="rounded-md bg-[#fff4d6] px-2 py-1 text-xs font-semibold text-[#745100]">未保存</span>}
                  </div>
                  <p className="mt-0.5 truncate text-label-sm text-on-surface-variant">{unit.document_name}</p>
                </div>
                <div className="flex items-center gap-1">
                  <IconButton label="上一条（Alt+←）" disabled={selectedIndex <= 0} onClick={() => move(-1)}><ArrowLeft className="h-4 w-4" /></IconButton>
                  <span className="min-w-16 text-center font-mono text-xs tabular-nums text-on-surface-variant">{selectedIndex + 1}/{units.length}</span>
                  <IconButton label="下一条（Alt+→）" disabled={selectedIndex < 0 || selectedIndex >= units.length - 1} onClick={() => move(1)}><ArrowRight className="h-4 w-4" /></IconButton>
                </div>
              </div>

              {feedback && <div role="status" aria-live="polite" className={`mx-4 mt-3 flex shrink-0 items-start gap-2 rounded-lg border px-3 py-2 text-label-sm md:mx-5 ${feedback.type === 'success' ? 'border-[#b8ddc5] bg-[#edf9f1] text-[#155b31]' : 'border-error/25 bg-error-container/60 text-on-error-container'}`}>
                {feedback.type === 'success' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
                <span className="flex-1">{feedback.message}</span>
                <button type="button" onClick={() => setFeedback(null)} className="-m-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-md" aria-label="关闭提示"><X className="h-4 w-4" /></button>
              </div>}

              <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-4 md:p-5">
                <div className="grid items-start gap-4 xl:grid-cols-[minmax(280px,0.72fr)_minmax(540px,1.28fr)]">
                  <div className="space-y-4 xl:sticky xl:top-0">
                    <SourcePanel unit={unit} />
                    <ValidationPanel validation={validation} dirty={dirty} onValidate={() => void validateDraft()} validating={validating} />
                    <ReviewPanel unit={unit} reviewer={reviewer} reviewNote={reviewNote} onReviewerChange={setReviewer} onReviewNoteChange={setReviewNote} onNotesChange={(notes) => setEditedUnit({ ...unit, adjudication_notes: notes })} />
                  </div>
                  <RuleEditor unit={unit} vocabularies={summary?.vocabularies || {}} validation={validation} onChange={setEditedUnit} />
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-outline-variant/50 bg-surface-container-lowest px-4 py-2.5 shadow-[0_-8px_30px_rgba(0,0,0,0.04)] md:px-5">
                <div className="text-xs text-on-surface-variant">
                  {validation?.valid ? <span className="flex items-center gap-1.5 font-semibold text-[#17633a]"><CheckCircle2 className="h-4 w-4" />当前版本严格校验通过</span> : <span className="flex items-center gap-1.5 font-semibold text-error"><AlertCircle className="h-4 w-4" />当前版本仍有 {validation?.error_count || 0} 个错误</span>}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => void validateDraft()} disabled={validating || saving} className="flex h-11 items-center gap-2 rounded-lg border border-outline-variant bg-surface px-4 text-label-md font-semibold transition-colors hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-45"><ClipboardCheck className="h-4 w-4" />严格校验</button>
                  <button type="button" onClick={() => void save('in_progress')} disabled={saving || (!dirty && !reviewNote.trim())} className="flex h-11 items-center gap-2 rounded-lg border border-primary bg-surface px-4 text-label-md font-semibold text-primary transition-colors hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-45">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}保存进度</button>
                  <button type="button" onClick={() => void save('human_reviewed')} disabled={saving || validating || Boolean(validation && !validation.valid)} className="flex h-11 items-center gap-2 rounded-lg bg-primary px-4 text-label-md font-bold text-on-primary transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-35"><Check className="h-4 w-4" />保存并标记通过</button>
                </div>
              </div>
            </div>
          ) : <EmptyList message="请选择一个标注单元开始审查" />}
        </main>
      </div>
    </section>
  );
}

function RuleEditor({ unit, vocabularies, validation, onChange }: { unit: GoldUnit; vocabularies: Record<string, string[]>; validation: ValidationResult | null; onChange: (unit: GoldUnit) => void }) {
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
  const rules = unit.gold_answer.制度规则;
  const updateRules = (next: GoldRule[]) => onChange({ ...unit, gold_answer: { ...unit.gold_answer, 制度规则: next } });
  const updateRule = (index: number, next: GoldRule) => updateRules(rules.map((rule, ruleIndex) => ruleIndex === index ? next : rule));

  return (
    <div className="rounded-xl border border-outline-variant/50 bg-surface-container-lowest">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant/40 px-4 py-3">
        <div>
          <h2 className="text-body-md font-bold">嵌套制度规则</h2>
          <p className="mt-0.5 text-xs text-on-surface-variant">所有证据字段应直接来自本条原文；空数组表示该实体族不存在。</p>
        </div>
        <button type="button" onClick={() => updateRules([...rules, structuredClone(EMPTY_RULE)])} className="flex h-11 items-center gap-2 rounded-lg border border-outline-variant px-3 text-label-sm font-semibold hover:bg-surface-container"><Plus className="h-4 w-4" />新增规则</button>
      </div>
      <div className="space-y-3 p-3 md:p-4">
        {rules.length ? rules.map((rule, index) => {
          const issueCount = validation?.issues.filter((issue) => issue.path.startsWith(`gold_answer.制度规则.${index}`)).length || 0;
          const isCollapsed = collapsed[index];
          return (
            <article key={index} className="overflow-hidden rounded-xl border border-outline-variant/60 bg-surface">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-outline-variant/40 bg-surface-container-low px-3 py-2">
                <button type="button" onClick={() => setCollapsed((value) => ({ ...value, [index]: !value[index] }))} className="flex min-h-11 items-center gap-2 text-left font-semibold">
                  {isCollapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
                  <span className="font-mono text-xs text-on-surface-variant">RULE {String(index + 1).padStart(2, '0')}</span>
                  <span>{rule.规则类型 || '未选择类型'}</span>
                  {issueCount > 0 && <span className="rounded-md bg-error-container px-2 py-0.5 text-xs font-semibold text-on-error-container">{issueCount} 问题</span>}
                </button>
                <div className="flex gap-1">
                  <IconButton label="复制此规则" onClick={() => updateRules([...rules.slice(0, index + 1), structuredClone(rule), ...rules.slice(index + 1)])}><Copy className="h-4 w-4" /></IconButton>
                  <IconButton label="删除此规则" tone="danger" onClick={() => { if (window.confirm(`确定删除规则 ${index + 1} 吗？`)) updateRules(rules.filter((_, ruleIndex) => ruleIndex !== index)); }}><Trash2 className="h-4 w-4" /></IconButton>
                </div>
              </div>
              {!isCollapsed && <div className="space-y-4 p-3 md:p-4">
                <label className="block max-w-sm">
                  <span className="mb-1.5 block text-xs font-bold text-on-surface-variant">规则类型</span>
                  <select value={rule.规则类型 || ''} onChange={(event) => updateRule(index, { ...rule, 规则类型: event.target.value || null })} className="h-11 w-full rounded-lg border border-outline-variant bg-surface-container-lowest px-3 text-label-md outline-none focus:border-primary focus:ring-2 focus:ring-primary/15">
                    <option value="">未选择</option>
                    {(vocabularies.规则类型 || []).map((value) => <option key={value}>{value}</option>)}
                  </select>
                </label>
                {ENTITY_SECTIONS.map((section) => (
                  <EntitySection key={section.key} title={section.title} description={section.description} fields={section.fields} items={rule[section.key]} vocabularies={vocabularies} onChange={(items) => updateRule(index, { ...rule, [section.key]: items })} onAdd={() => updateRule(index, { ...rule, [section.key]: [...rule[section.key], structuredClone(section.empty)] })} />
                ))}
              </div>}
            </article>
          );
        }) : (
          <div className="rounded-lg border border-dashed border-outline-variant p-8 text-center">
            <CircleDashed className="mx-auto h-7 w-7 text-on-surface-variant" />
            <p className="mt-2 font-semibold">该单元当前没有制度规则</p>
            <p className="mt-1 text-label-sm text-on-surface-variant">如果原文确实不包含可抽取规则，可保留为空作为负样本。</p>
          </div>
        )}
      </div>
    </div>
  );
}

function EntitySection({ title, description, fields, items, vocabularies, onChange, onAdd }: {
  key?: React.Key;
  title: string;
  description: string;
  fields: Array<{ key: string; label: string; vocabulary?: string; aliases?: boolean; wide?: boolean }>;
  items: GoldEntity[];
  vocabularies: Record<string, string[]>;
  onChange: (items: GoldEntity[]) => void;
  onAdd: () => void;
}) {
  const updateItem = (index: number, key: string, value: NullableText | string[]) => onChange(items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  return (
    <fieldset className="rounded-lg border border-outline-variant/50 p-3">
      <legend className="px-1 text-label-sm font-bold">{title} <span className="font-normal text-on-surface-variant">({items.length})</span></legend>
      <div className="-mt-1 mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-on-surface-variant">{description}</p>
        <button type="button" onClick={onAdd} className="flex h-10 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold hover:bg-surface-container"><Plus className="h-3.5 w-3.5" />添加{title}</button>
      </div>
      {items.length ? <div className="space-y-2.5">{items.map((item, index) => (
        <div key={index} className="grid gap-2 rounded-lg bg-surface-container-low p-2.5 sm:grid-cols-2">
          {fields.map((field) => (
            <label key={field.key} className={field.wide ? 'sm:col-span-2' : ''}>
              <span className="mb-1 block text-[11px] font-semibold text-on-surface-variant">{field.label}</span>
              {field.vocabulary ? (
                <select value={String(item[field.key] ?? '')} onChange={(event) => updateItem(index, field.key, event.target.value || null)} className="h-10 w-full rounded-md border border-outline-variant bg-surface-container-lowest px-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15">
                  <option value="">未选择</option>
                  {(vocabularies[field.vocabulary] || []).map((value) => <option key={value}>{value}</option>)}
                </select>
              ) : (
                <input value={field.aliases ? (Array.isArray(item[field.key]) ? (item[field.key] as string[]).join('、') : '') : String(item[field.key] ?? '')} onChange={(event) => updateItem(index, field.key, field.aliases ? event.target.value.split(/[,，、]/).map((value) => value.trim()).filter(Boolean) : (event.target.value || null))} className="h-10 w-full rounded-md border border-outline-variant bg-surface-container-lowest px-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" placeholder={field.aliases ? '多个别名用顿号分隔' : '未标注时留空'} />
              )}
            </label>
          ))}
          <button type="button" onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))} className="flex h-10 items-center justify-center gap-1.5 rounded-md border border-error/20 text-xs font-semibold text-error hover:bg-error-container sm:col-span-2" aria-label={`删除第 ${index + 1} 个${title}`}><Trash2 className="h-3.5 w-3.5" />删除此项</button>
        </div>
      ))}</div> : <p className="rounded-md bg-surface-container-low px-3 py-2 text-xs text-on-surface-variant">无{title}；确认原文没有该类信息时可保持为空。</p>}
    </fieldset>
  );
}

function SourcePanel({ unit }: { unit: GoldUnit }) {
  return <section className="rounded-xl border border-outline-variant/50 bg-surface-container-lowest p-4">
    <div className="flex items-center justify-between gap-2"><h2 className="flex items-center gap-2 text-body-md font-bold"><FileText className="h-4 w-4" />原文证据</h2><span className="font-mono text-[11px] text-on-surface-variant">{unit.document_id}</span></div>
    {unit.context?.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{unit.context.map((item, index) => <span key={index} className="rounded-md bg-surface-container px-2 py-1 text-xs font-medium text-on-surface-variant">{item.title || item.number}</span>)}</div>}
    <blockquote className="mt-3 whitespace-pre-wrap rounded-lg border-l-4 border-primary bg-surface-container-low p-3 text-[15px] leading-7 text-on-surface">{unit.input_text}</blockquote>
    {unit.source_text !== unit.input_text && <details className="mt-3"><summary className="cursor-pointer text-xs font-semibold text-on-surface-variant">查看完整 source_text</summary><p className="mt-2 whitespace-pre-wrap text-sm leading-6">{unit.source_text}</p></details>}
    <div className="mt-3 border-t border-outline-variant/40 pt-3 text-[11px] leading-5 text-on-surface-variant"><div className="truncate" title={unit.source_markdown}>来源：{unit.source_markdown}</div><div className="truncate font-mono" title={unit.source_sha256}>SHA-256：{unit.source_sha256}</div></div>
  </section>;
}

function ValidationPanel({ validation, dirty, onValidate, validating }: { validation: ValidationResult | null; dirty: boolean; onValidate: () => void; validating: boolean }) {
  const [expanded, setExpanded] = useState(true);
  return <section className="rounded-xl border border-outline-variant/50 bg-surface-container-lowest p-4">
    <div className="flex items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-body-md font-bold"><ClipboardCheck className="h-4 w-4" />严格校验</h2>
      <button type="button" onClick={onValidate} disabled={validating} className="flex h-10 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold hover:bg-surface-container disabled:opacity-45">{validating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}重新校验</button>
    </div>
    <button type="button" onClick={() => setExpanded(!expanded)} className={`mt-3 flex min-h-11 w-full items-center justify-between rounded-lg border px-3 text-left text-label-sm font-semibold ${validation?.valid ? 'border-[#b8ddc5] bg-[#edf9f1] text-[#155b31]' : 'border-error/25 bg-error-container/50 text-on-error-container'}`}>
      <span className="flex items-center gap-2">{validation?.valid ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}{validation?.valid ? '校验通过' : `${validation?.error_count || 0} 个严格错误`}{dirty && <span className="font-normal">（修改后待重检）</span>}</span>
      {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
    </button>
    {expanded && <div className="mt-2 space-y-2">{validation?.issues.length ? validation.issues.map((issue, index) => <div key={`${issue.path}-${index}`} className="rounded-lg border border-error/15 bg-error-container/30 p-2.5"><p className="text-xs font-semibold text-on-error-container">{issue.message}</p><code className="mt-1 block break-all text-[10px] text-on-surface-variant">{issue.path}</code></div>) : <p className="text-xs leading-5 text-on-surface-variant">已检查 schema 形状、原文证据值、受控词表及核心语义约束。</p>}</div>}
  </section>;
}

function ReviewPanel({ unit, reviewer, reviewNote, onReviewerChange, onReviewNoteChange, onNotesChange }: { unit: GoldUnit; reviewer: string; reviewNote: string; onReviewerChange: (value: string) => void; onReviewNoteChange: (value: string) => void; onNotesChange: (value: string[]) => void }) {
  return <section className="rounded-xl border border-outline-variant/50 bg-surface-container-lowest p-4">
    <h2 className="flex items-center gap-2 text-body-md font-bold"><ShieldCheck className="h-4 w-4" />审查记录</h2>
    <div className="mt-3 space-y-3">
      <label className="block"><span className="mb-1 block text-xs font-semibold text-on-surface-variant">审查人</span><input value={reviewer} onChange={(event) => onReviewerChange(event.target.value)} className="h-11 w-full rounded-lg border border-outline-variant bg-surface px-3 text-label-md outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" /></label>
      <label className="block"><span className="mb-1 block text-xs font-semibold text-on-surface-variant">裁决备注（每行一条，随数据保存）</span><textarea value={(unit.adjudication_notes || []).join('\n')} onChange={(event) => onNotesChange(event.target.value.split('\n').map((value) => value.trim()).filter(Boolean))} rows={3} className="w-full resize-y rounded-lg border border-outline-variant bg-surface p-3 text-sm leading-6 outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" placeholder="记录争议点、修订依据或边界判断" /></label>
      <label className="block"><span className="mb-1 block text-xs font-semibold text-on-surface-variant">本次审查说明</span><textarea value={reviewNote} onChange={(event) => onReviewNoteChange(event.target.value)} rows={2} className="w-full resize-y rounded-lg border border-outline-variant bg-surface p-3 text-sm leading-6 outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" placeholder="写入 review_history，不覆盖之前记录" /></label>
      {unit.reviewed_at && <p className="text-xs text-on-surface-variant">上次保存：{unit.reviewed_by || '未知'} · {new Date(unit.reviewed_at).toLocaleString('zh-CN')}</p>}
    </div>
  </section>;
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: 'success' | 'warning' }) {
  const toneClass = tone === 'success' ? 'border-[#b8ddc5] bg-[#edf9f1] text-[#155b31]' : tone === 'warning' ? 'border-[#ead49a] bg-[#fff8e5] text-[#745100]' : 'border-outline-variant/60 bg-surface-container-low text-on-surface';
  return <div className={`rounded-lg border px-3 py-1.5 ${toneClass}`}><span className="text-xs opacity-70">{label}</span><span className="ml-2 font-mono text-sm font-bold">{value}</span></div>;
}

function StatusIcon({ status }: { status: ReviewStatus }) {
  if (status === 'human_reviewed') return <CheckCircle2 className="h-4 w-4 shrink-0" />;
  if (status === 'in_progress') return <CircleDashed className="h-4 w-4 shrink-0" />;
  return <ClipboardCheck className="h-4 w-4 shrink-0" />;
}

function StatusBadge({ status }: { status: ReviewStatus }) {
  const style = status === 'human_reviewed' ? 'border-[#b8ddc5] bg-[#edf9f1] text-[#155b31]' : status === 'in_progress' ? 'border-[#ead49a] bg-[#fff8e5] text-[#745100]' : 'border-outline-variant bg-surface-container text-on-surface-variant';
  return <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold ${style}`}><StatusIcon status={status} />{STATUS_LABELS[status]}</span>;
}

function FilterSelect({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: React.ReactNode }) {
  return <label className="min-w-0"><span className="sr-only">{label}</span><div className="relative"><Filter className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-on-surface-variant" /><select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 w-full appearance-none truncate rounded-lg border border-outline-variant bg-surface pl-8 pr-7 text-xs font-medium outline-none focus:border-primary focus:ring-2 focus:ring-primary/15">{children}</select><ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2" /></div></label>;
}

function IconButton({ label, onClick, disabled, tone, children }: { label: string; onClick: () => void; disabled?: boolean; tone?: 'danger'; children: React.ReactNode }) {
  return <button type="button" onClick={onClick} disabled={disabled} className={`flex h-11 w-11 items-center justify-center rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-30 ${tone === 'danger' ? 'text-error hover:bg-error-container' : 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface'}`} aria-label={label} title={label}>{children}</button>;
}

function EmptyList({ message = '没有符合当前筛选条件的标注单元' }: { message?: string }) {
  return <div className="flex min-h-48 flex-col items-center justify-center p-6 text-center text-on-surface-variant"><CircleDashed className="h-7 w-7" /><p className="mt-2 text-label-sm font-medium">{message}</p></div>;
}
