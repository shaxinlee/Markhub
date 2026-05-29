/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Check, Globe2, Languages, Type } from 'lucide-react';
import type { ReactNode } from 'react';

interface SettingsPageProps {
  language: 'zh-CN';
  onLanguageChange: (language: 'zh-CN') => void;
}

export default function SettingsPage({ language, onLanguageChange }: SettingsPageProps) {
  return (
    <section className="markhub-settings w-full overflow-y-auto bg-surface-container-low p-gutter text-on-surface md:p-[40px]">
      <div className="mx-auto max-w-7xl space-y-[40px]">
        <section className="rounded-[1.5rem] border border-surface-variant bg-surface-container-lowest p-[32px] md:p-[40px]">
          <div className="mb-10 flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <div>
              <span className="text-label-sm font-bold uppercase tracking-[0.24em] text-on-surface-variant">System Preferences</span>
              <h1 className="mt-3 text-headline-lg font-semibold text-primary">设置</h1>
              <p className="mt-2 max-w-2xl text-body-md text-on-surface-variant">
                管理 MarkHub 的界面语言和中文字体。提示词请在“提示词管理”页面统一维护。
              </p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-[0.75rem] bg-surface-container-high text-primary">
              <Globe2 className="h-6 w-6" />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-8">
              <SettingsCard
                icon={<Languages className="h-5 w-5" />}
                title="语言"
                description="选择网页显示语言。当前只开放中文，后续可以继续扩展英文或更多语言。"
                badge="默认中文"
              >
                <label htmlFor="languageSelect" className="block text-label-sm font-semibold text-on-surface-variant">
                  界面语言
                  <select
                    id="languageSelect"
                    value={language}
                    onChange={(event) => onLanguageChange(event.target.value as 'zh-CN')}
                    className="mt-2 w-full max-w-md rounded-[0.75rem] border border-outline-variant/50 bg-surface-container px-3 py-2.5 text-label-md text-on-surface outline-none focus:border-primary"
                  >
                    <option value="zh-CN">中文（简体）</option>
                  </select>
                </label>
                <div className="mt-5 flex items-center gap-2 text-label-md font-semibold text-on-surface-variant">
                  <Check className="h-4 w-4 text-primary" />
                  <span>当前网页语言已设置为 zh-CN</span>
                </div>
              </SettingsCard>

              <SettingsCard
                icon={<Type className="h-5 w-5" />}
                title="中文字体"
                description="默认字体使用 Noto Sans SC，并回退到 PingFang SC、Microsoft YaHei。"
              >
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div className="rounded-[0.75rem] border border-outline-variant/40 bg-surface-container p-5">
                    <span className="text-label-sm font-bold uppercase tracking-[0.2em] text-on-surface-variant">Preview</span>
                    <p className="mt-4 text-headline-md font-bold text-primary">Markhub 智能文档标注平台</p>
                    <p className="mt-2 text-label-md leading-6 text-on-surface-variant">
                      中文界面默认启用，适合长文本、表格、标题层级和版面分析结果展示。
                    </p>
                  </div>
                  <div className="rounded-[0.75rem] border border-outline-variant/40 bg-surface-container p-5 font-mono">
                    <span className="text-label-sm font-bold uppercase tracking-[0.2em] text-on-surface-variant">Font Stack</span>
                    <p className="mt-4 break-words text-label-md leading-6 text-on-surface-variant">
                      Noto Sans SC, PingFang SC, Microsoft YaHei, Inter, system-ui, sans-serif
                    </p>
                  </div>
                </div>
              </SettingsCard>

            </div>

            <aside className="h-fit rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-6">
              <span className="text-label-sm font-bold uppercase tracking-[0.24em] text-on-surface-variant">Current</span>
              <div className="mt-5 space-y-4">
                <SummaryRow label="语言" value="中文（简体）" />
                <SummaryRow label="HTML Lang" value="zh-CN" mono />
                <SummaryRow label="主字体" value="Noto Sans SC" />
              </div>
            </aside>
          </div>
        </section>
      </div>
    </section>
  );
}

function SettingsCard({
  icon,
  title,
  description,
  badge,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[1.5rem] border border-outline-variant/40 bg-surface-container-lowest p-6">
      <div className="mb-5 flex items-start justify-between gap-6 border-b border-outline-variant/40 pb-5">
        <div>
          <div className="mb-2 flex items-center gap-2 text-primary">
            {icon}
            <h2 className="text-label-md font-bold uppercase tracking-[0.18em]">{title}</h2>
          </div>
          <p className="max-w-2xl text-label-md leading-6 text-on-surface-variant">{description}</p>
        </div>
        {badge && (
          <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-1 text-label-sm font-semibold text-primary">
            {badge}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

function SummaryRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4 border-b border-outline-variant/40 pb-3 last:border-b-0 last:pb-0">
      <span className="text-label-md text-on-surface-variant">{label}</span>
      <span className={`text-label-md font-bold text-primary ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}
