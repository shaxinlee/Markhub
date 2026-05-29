/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { Crosshair, FileEdit, FileText, Grid3X3, Save, Spline, Square } from 'lucide-react';
import { AnnotationFeature, PromptTemplateOption } from '../types';

const PROMPT_CATEGORY_META: Array<{
  id: AnnotationFeature;
  label: string;
  description: string;
  icon: React.ReactNode;
  available: boolean;
}> = [
  { id: 'bounding_box', label: 'Bounding Box', description: '矩形框标注提示词', icon: <Square className="h-4 w-4" />, available: false },
  { id: 'polygon', label: 'Polygon Segment', description: '多边形分割提示词', icon: <Spline className="h-4 w-4" />, available: false },
  { id: 'layout', label: 'Layout Analysis', description: '文档版面分析提示词', icon: <Grid3X3 className="h-4 w-4" />, available: true },
  { id: 'keypoints', label: 'Keypoints Picker', description: '关键点标注提示词', icon: <Crosshair className="h-4 w-4" />, available: false },
  { id: 'text_transcription', label: 'Text Transcription', description: '文字转录提示词', icon: <FileEdit className="h-4 w-4" />, available: false },
];

interface PromptTemplateManagerProps {
  promptTemplates: PromptTemplateOption[];
  onSavePromptTemplate: (template: PromptTemplateOption) => Promise<PromptTemplateOption>;
}

export default function PromptTemplateManager({ promptTemplates, onSavePromptTemplate }: PromptTemplateManagerProps) {
  const [activeCategory, setActiveCategory] = useState<AnnotationFeature>('layout');
  const [selectedTemplateId, setSelectedTemplateId] = useState('default_template_1');
  const [draftName, setDraftName] = useState('');
  const [draftPrompt, setDraftPrompt] = useState('');
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const categoryTemplates = promptTemplates.filter((template) => template.category === activeCategory);
  const selectedTemplate = categoryTemplates.find((template) => template.id === selectedTemplateId) || categoryTemplates[0];
  const activeMeta = PROMPT_CATEGORY_META.find((item) => item.id === activeCategory) || PROMPT_CATEGORY_META[2];

  useEffect(() => {
    if (categoryTemplates.length && !categoryTemplates.some((template) => template.id === selectedTemplateId)) {
      setSelectedTemplateId(categoryTemplates[0].id);
    }
  }, [activeCategory, categoryTemplates, selectedTemplateId]);

  useEffect(() => {
    setDraftName(selectedTemplate?.name || '');
    setDraftPrompt(selectedTemplate?.prompt || '');
    setSaveState('idle');
    setErrorMessage('');
  }, [selectedTemplate?.id, selectedTemplate?.name, selectedTemplate?.prompt]);

  const handleSave = async () => {
    if (!selectedTemplate || saveState === 'saving') return;
    setSaveState('saving');
    setErrorMessage('');
    try {
      await onSavePromptTemplate({ ...selectedTemplate, name: draftName.trim() || selectedTemplate.name, prompt: draftPrompt });
      setSaveState('saved');
    } catch (error) {
      setSaveState('error');
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const handleCreateTemplate = async () => {
    if (!activeMeta.available || saveState === 'saving') return;
    const nextIndex = categoryTemplates.length + 1;
    const newTemplate: PromptTemplateOption = {
      id: `${activeCategory}_template_${Date.now()}`,
      name: `${activeMeta.label} 模板 ${nextIndex}`,
      category: activeCategory,
      prompt: selectedTemplate?.prompt || draftPrompt,
    };
    setSaveState('saving');
    setErrorMessage('');
    try {
      const saved = await onSavePromptTemplate(newTemplate);
      setSelectedTemplateId(saved.id);
      setSaveState('saved');
    } catch (error) {
      setSaveState('error');
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <section className="rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-6">
      <div className="mb-5 flex items-start justify-between gap-6 border-b border-outline-variant/40 pb-5">
        <div>
          <div className="mb-2 flex items-center gap-2 text-primary">
            <FileText className="h-5 w-5" />
            <h2 className="text-label-md font-bold uppercase tracking-[0.18em]">提示词模板</h2>
          </div>
          <p className="max-w-2xl text-label-md leading-6 text-on-surface-variant">
            兼容旧版自动标注流程的模板设置。新的完整增删改查能力请使用“提示词管理”页面。
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-surface-container px-2.5 py-1 text-label-sm font-semibold text-on-surface-variant">
          {promptTemplates.length} Templates
        </span>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[260px_minmax(0,1fr)]">
        <div className="space-y-2">
          {PROMPT_CATEGORY_META.map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => setActiveCategory(category.id)}
              className={`w-full rounded-[0.75rem] border px-4 py-3 text-left transition-all active:scale-[0.99] ${
                activeCategory === category.id
                  ? 'border-primary bg-primary text-on-primary'
                  : 'border-outline-variant/50 bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container hover:text-primary'
              }`}
            >
              <div className="flex items-center gap-3">
                <span>{category.icon}</span>
                <span className="text-label-sm font-bold uppercase tracking-[0.16em]">{category.label}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className={activeCategory === category.id ? 'text-label-sm text-on-primary/75' : 'text-label-sm text-on-surface-variant'}>
                  {category.description}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${activeCategory === category.id ? 'bg-on-primary/15 text-on-primary' : 'bg-surface-container-high text-on-surface-variant'}`}>
                  {category.available ? 'Live' : 'Soon'}
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="min-h-[420px] rounded-[0.75rem] border border-outline-variant/40 bg-surface-container p-5">
          {categoryTemplates.length && selectedTemplate ? (
            <div className="flex h-full flex-col">
              <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <span className="text-label-sm font-bold uppercase tracking-[0.2em] text-on-surface-variant">{activeMeta.label}</span>
                  <h3 className="mt-2 text-headline-sm font-semibold text-primary">{selectedTemplate.name}</h3>
                </div>
                <div className="flex flex-col gap-2 md:min-w-[280px]">
                  <select
                    value={selectedTemplate.id}
                    onChange={(event) => setSelectedTemplateId(event.target.value)}
                    className="rounded-[0.75rem] border border-outline-variant/50 bg-surface-container-lowest px-3 py-2 text-label-md text-on-surface outline-none focus:border-primary"
                  >
                    {categoryTemplates.map((template) => (
                      <option key={template.id} value={template.id}>{template.name}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={handleCreateTemplate}
                    disabled={!activeMeta.available || saveState === 'saving'}
                    className="rounded-[0.75rem] border border-outline-variant/50 px-3 py-2 text-label-sm font-bold text-primary transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    新建当前提示词副本
                  </button>
                </div>
              </div>

              <label htmlFor="promptTemplateName" className="mb-2 block text-label-sm font-semibold text-on-surface-variant">
                Template Name
              </label>
              <input
                id="promptTemplateName"
                value={draftName}
                onChange={(event) => {
                  setDraftName(event.target.value);
                  setSaveState('idle');
                }}
                className="mb-4 w-full rounded-[0.75rem] border border-outline-variant/50 bg-surface-container-lowest px-4 py-2.5 text-label-md text-on-surface outline-none focus:border-primary"
              />

              <label htmlFor="promptTemplateEditor" className="mb-2 block text-label-sm font-semibold text-on-surface-variant">
                Prompt Content
              </label>
              <textarea
                id="promptTemplateEditor"
                value={draftPrompt}
                onChange={(event) => {
                  setDraftPrompt(event.target.value);
                  setSaveState('idle');
                }}
                className="min-h-[280px] flex-1 resize-none rounded-[0.75rem] border border-outline-variant/50 bg-surface-container-lowest p-4 font-mono text-xs leading-6 text-on-surface outline-none focus:border-primary"
                spellCheck={false}
              />

              <div className="mt-4 flex flex-col gap-3 border-t border-outline-variant/40 pt-4 md:flex-row md:items-center md:justify-between">
                <p className={`text-label-sm ${saveState === 'error' ? 'text-error' : saveState === 'saved' ? 'text-primary' : 'text-on-surface-variant'}`}>
                  {saveState === 'saving' ? '正在保存提示词模板...' : saveState === 'saved' ? '已保存，后续 Layout 分析会使用这份提示词。' : saveState === 'error' ? errorMessage : '修改后点击保存即可更新后端模板。'}
                </p>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saveState === 'saving'}
                  className="inline-flex items-center justify-center gap-2 rounded-[0.75rem] bg-primary px-5 py-2.5 text-label-md font-bold text-on-primary transition-all hover:bg-primary/90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Save className="h-4 w-4" />
                  保存提示词
                </button>
              </div>
            </div>
          ) : (
            <div className="flex h-full min-h-[360px] flex-col items-center justify-center text-center">
              <div className="mb-4 text-on-surface-variant">{activeMeta.icon}</div>
              <h3 className="text-headline-sm font-semibold text-primary">功能未上线</h3>
              <p className="mt-2 max-w-sm text-label-md leading-6 text-on-surface-variant">
                {activeMeta.label} 的提示词模板会在对应标注能力上线后开放编辑。
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
