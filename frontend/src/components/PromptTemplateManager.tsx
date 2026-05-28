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
  { id: 'bounding_box', label: 'Bounding Box', description: '矩形框标注提示词', icon: <Square className="w-4 h-4" />, available: false },
  { id: 'polygon', label: 'Polygon Segment', description: '多边形分割提示词', icon: <Spline className="w-4 h-4" />, available: false },
  { id: 'layout', label: 'Layout Analysis', description: '文档版面分析提示词', icon: <Grid3X3 className="w-4 h-4" />, available: true },
  { id: 'keypoints', label: 'Keypoints Picker', description: '关键点标注提示词', icon: <Crosshair className="w-4 h-4" />, available: false },
  { id: 'text_transcription', label: 'Text Transcription', description: '文字转录提示词', icon: <FileEdit className="w-4 h-4" />, available: false },
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
    <div className="bg-[#141414] border border-white/10 rounded-none p-6">
      <div className="flex items-start justify-between gap-6 border-b border-white/10 pb-5 mb-5">
        <div>
          <div className="flex items-center gap-2 text-white mb-2">
            <FileText className="w-5 h-5" />
            <h2 className="text-sm uppercase tracking-[0.2em] font-bold">提示词模板</h2>
          </div>
          <p className="text-xs text-white/50 leading-relaxed max-w-2xl">
            按标注类型维护模型提示词。当前已上线 Layout Analysis，所以“默认模板 1”归类在 Layout 提示词中，并会用于后续文档版面分析。
          </p>
        </div>
        <span className="text-[9px] uppercase tracking-[0.2em] font-mono text-white/45 bg-white/[0.03] border border-white/10 px-2 py-1">
          {promptTemplates.length} Templates
        </span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[260px_minmax(0,1fr)] gap-5">
        <div className="space-y-2">
          {PROMPT_CATEGORY_META.map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => setActiveCategory(category.id)}
              className={`w-full border px-4 py-3 text-left transition-all active:scale-[0.99] ${
                activeCategory === category.id
                  ? 'border-white/25 bg-white/[0.08] text-white'
                  : 'border-white/10 bg-white/[0.02] text-white/55 hover:bg-white/[0.04] hover:text-white/80'
              }`}
            >
              <div className="flex items-center gap-3">
                <span className={category.available ? 'text-emerald-300' : 'text-white/35'}>{category.icon}</span>
                <span className="text-[10px] uppercase tracking-[0.18em] font-bold">{category.label}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-[11px] text-white/40">{category.description}</span>
                <span className={`text-[8px] uppercase tracking-[0.14em] font-mono ${category.available ? 'text-emerald-300' : 'text-white/25'}`}>
                  {category.available ? 'Live' : 'Soon'}
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="min-h-[420px] border border-white/10 bg-[#0e0e0e] p-5">
          {categoryTemplates.length && selectedTemplate ? (
            <div className="flex h-full flex-col">
              <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <span className="text-[10px] uppercase tracking-[0.25em] text-white/35 font-mono">{activeMeta.label}</span>
                  <h3 className="mt-2 font-serif italic text-xl text-white">{selectedTemplate.name}</h3>
                </div>
                <div className="flex flex-col gap-2 md:min-w-[280px]">
                  <select
                    value={selectedTemplate.id}
                    onChange={(event) => setSelectedTemplateId(event.target.value)}
                    className="bg-[#141414] border border-white/10 rounded-none px-3 py-2 text-xs text-white focus:outline-none focus:border-white/30"
                  >
                    {categoryTemplates.map((template) => (
                      <option key={template.id} value={template.id}>{template.name}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={handleCreateTemplate}
                    disabled={!activeMeta.available || saveState === 'saving'}
                    className="border border-white/10 bg-white/[0.03] px-3 py-2 text-[10px] font-bold uppercase tracking-[0.16em] text-white/70 transition-colors hover:bg-white/[0.08] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    新建当前提示词副本
                  </button>
                </div>
              </div>

              <label htmlFor="promptTemplateName" className="mb-2 block text-[10px] uppercase tracking-wider font-bold text-white/45">
                Template Name
              </label>
              <input
                id="promptTemplateName"
                value={draftName}
                onChange={(event) => {
                  setDraftName(event.target.value);
                  setSaveState('idle');
                }}
                className="mb-4 w-full bg-black/20 border border-white/10 rounded-none px-4 py-2.5 text-xs text-white/80 outline-none focus:border-white/30"
              />

              <label htmlFor="promptTemplateEditor" className="mb-2 block text-[10px] uppercase tracking-wider font-bold text-white/45">
                Prompt Content
              </label>
              <textarea
                id="promptTemplateEditor"
                value={draftPrompt}
                onChange={(event) => {
                  setDraftPrompt(event.target.value);
                  setSaveState('idle');
                }}
                className="min-h-[280px] flex-1 resize-none bg-black/20 border border-white/10 rounded-none p-4 text-xs leading-6 text-white/80 outline-none focus:border-white/30 custom-scrollbar"
                spellCheck={false}
              />

              <div className="mt-4 flex flex-col gap-3 border-t border-white/10 pt-4 md:flex-row md:items-center md:justify-between">
                <p className={`text-[11px] ${saveState === 'error' ? 'text-red-300' : saveState === 'saved' ? 'text-emerald-300' : 'text-white/40'}`}>
                  {saveState === 'saving' ? '正在保存提示词模板...' : saveState === 'saved' ? '已保存，后续 Layout 分析会使用这份提示词。' : saveState === 'error' ? errorMessage : '修改后点击保存即可更新后端模板。'}
                </p>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saveState === 'saving'}
                  className="inline-flex items-center justify-center gap-2 bg-white px-5 py-2.5 text-[10px] font-bold uppercase tracking-[0.18em] text-black transition-all hover:bg-white/90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Save className="w-4 h-4" />
                  Save Prompt
                </button>
              </div>
            </div>
          ) : (
            <div className="flex h-full min-h-[360px] flex-col items-center justify-center text-center">
              <div className="mb-4 text-white/25">{activeMeta.icon}</div>
              <h3 className="font-serif italic text-xl text-white/80">功能未上线</h3>
              <p className="mt-2 max-w-sm text-xs leading-6 text-white/45">
                {activeMeta.label} 的提示词模板会在对应标注能力上线后开放编辑。
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
