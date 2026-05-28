/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Check, Globe2, Languages, Type } from 'lucide-react';
import { PromptTemplateOption } from '../types';
import PromptTemplateManager from './PromptTemplateManager';

interface SettingsPageProps {
  language: 'zh-CN';
  promptTemplates: PromptTemplateOption[];
  onLanguageChange: (language: 'zh-CN') => void;
  onSavePromptTemplate: (template: PromptTemplateOption) => Promise<PromptTemplateOption>;
}

export default function SettingsPage({ language, promptTemplates, onLanguageChange, onSavePromptTemplate }: SettingsPageProps) {
  return (
    <section className="markhub-settings flex flex-1 overflow-y-auto custom-scrollbar bg-surface-container-low text-on-surface">
      <aside className="w-20 bg-[#0e0e0e] border-r border-white/10 flex flex-col items-center py-10 space-y-12 h-full select-none z-10">
        <div className="p-3 text-white bg-white/10 border border-white/5 rounded-none transition-all">
          <Globe2 className="w-5 h-5" />
        </div>
      </aside>

      <div className="flex-1 px-12 py-12 space-y-10">
        <div className="border-b border-white/10 pb-8">
          <span className="text-[10px] uppercase tracking-[0.3em] text-white/40 font-mono">System Preferences</span>
          <h1 className="font-serif italic text-4xl leading-tight text-white tracking-tight mt-3">
            设置
          </h1>
          <p className="text-white/55 text-sm max-w-2xl mt-3 leading-relaxed">
            管理 Markhub 的界面语言和显示字体。当前版本默认使用中文界面，并采用适合商业产品的中文字体栈。
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-8">
          <div className="space-y-8">
            <div className="bg-[#141414] border border-white/10 rounded-none p-6">
              <div className="flex items-start justify-between gap-6 border-b border-white/10 pb-5 mb-5">
                <div>
                  <div className="flex items-center gap-2 text-white mb-2">
                    <Languages className="w-5 h-5" />
                    <h2 className="text-sm uppercase tracking-[0.2em] font-bold">语言</h2>
                  </div>
                  <p className="text-xs text-white/50 leading-relaxed">
                    选择网页显示语言。当前只开放中文，后续可以继续扩展英文或更多语言。
                  </p>
                </div>
                <span className="text-[9px] uppercase tracking-[0.2em] font-mono text-emerald-300 bg-emerald-400/10 border border-emerald-400/20 px-2 py-1">
                  默认中文
                </span>
              </div>

              <label htmlFor="languageSelect" className="block text-[10px] uppercase tracking-wider font-bold text-white/50 mb-2">
                界面语言
              </label>
              <select
                id="languageSelect"
                value={language}
                onChange={(event) => onLanguageChange(event.target.value as 'zh-CN')}
                className="w-full max-w-md bg-[#0e0e0e] border border-white/10 rounded-none px-3 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 font-medium"
              >
                <option value="zh-CN">中文（简体）</option>
              </select>

              <div className="mt-5 flex items-center gap-2 text-[11px] text-white/45 font-mono">
                <Check className="w-4 h-4 text-emerald-300" />
                <span>当前网页语言已设置为 zh-CN</span>
              </div>
            </div>

            <div className="bg-[#141414] border border-white/10 rounded-none p-6">
              <div className="flex items-center gap-2 text-white mb-2">
                <Type className="w-5 h-5" />
                <h2 className="text-sm uppercase tracking-[0.2em] font-bold">中文字体</h2>
              </div>
              <p className="text-xs text-white/50 leading-relaxed max-w-2xl">
                默认字体使用 `Noto Sans SC`，并回退到 `PingFang SC`、`Microsoft YaHei`。`Noto Sans SC` 对应思源黑体体系，开源可商用，适合中文后台、数据标注平台和企业级应用界面。
              </p>

              <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border border-white/10 bg-white/[0.02] p-5">
                  <span className="text-[10px] uppercase tracking-[0.24em] text-white/40 font-mono">Preview</span>
                  <p className="mt-4 text-2xl font-bold text-white tracking-normal">
                    Markhub 智能文档标注平台
                  </p>
                  <p className="mt-2 text-sm text-white/55 leading-7">
                    中文界面默认启用，适合长文本、表格、标题层级和版面分析结果展示。
                  </p>
                </div>
                <div className="border border-white/10 bg-white/[0.02] p-5 font-mono">
                  <span className="text-[10px] uppercase tracking-[0.24em] text-white/40">Font Stack</span>
                  <p className="mt-4 text-xs leading-6 text-white/60 break-words">
                    Noto Sans SC, PingFang SC, Microsoft YaHei, Inter, system-ui, sans-serif
                  </p>
                </div>
              </div>
            </div>

            <PromptTemplateManager
              promptTemplates={promptTemplates}
              onSavePromptTemplate={onSavePromptTemplate}
            />
          </div>

          <aside className="bg-[#141414] border border-white/10 rounded-none p-6 h-fit">
            <span className="text-[10px] uppercase tracking-[0.3em] text-white/40 font-mono">Current</span>
            <div className="mt-5 space-y-4">
              <div className="flex justify-between items-center border-b border-white/10 pb-3">
                <span className="text-xs text-white/45">语言</span>
                <span className="text-xs text-white font-bold">中文（简体）</span>
              </div>
              <div className="flex justify-between items-center border-b border-white/10 pb-3">
                <span className="text-xs text-white/45">HTML Lang</span>
                <span className="text-xs text-white font-mono">zh-CN</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-white/45">主字体</span>
                <span className="text-xs text-white font-bold">Noto Sans SC</span>
              </div>
              <div className="flex justify-between items-center border-t border-white/10 pt-3">
                <span className="text-xs text-white/45">Layout 提示词</span>
                <span className="text-xs text-white font-bold">
                  {promptTemplates.filter((template) => template.category === 'layout').length}
                </span>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
