import React from 'react';
import { Bell, Search, UserCircle } from 'lucide-react';

export type AppTab = 'projects' | 'datasets' | 'prompts' | 'analytics' | 'team' | 'settings';

const NAV_ITEMS: Array<{ id: AppTab; label: string }> = [
  { id: 'projects', label: '项目' },
  { id: 'datasets', label: '数据集' },
  { id: 'prompts', label: '提示词管理' },
  { id: 'analytics', label: '分析' },
  { id: 'team', label: '团队' },
  { id: 'settings', label: '设置' },
];

interface AppShellProps {
  activeTab: AppTab;
  onNavigate: (tab: AppTab) => void;
  children: React.ReactNode;
}

export default function AppShell({ activeTab, onNavigate, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-surface-container-low text-on-surface font-sans">
      <div className="pointer-events-none fixed inset-x-0 bottom-0 h-[360px] bg-gradient-to-t from-on-tertiary-container/10 via-primary/5 to-transparent blur-[120px]" />

      <header className="sticky top-0 z-50 border-b border-outline-variant/30 bg-surface/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-[1920px] items-center justify-between px-container-mobile md:px-container-desktop">
          <div className="flex min-w-0 items-center gap-8">
            <button
              type="button"
              onClick={() => onNavigate('projects')}
              className="shrink-0 text-headline-md font-bold tracking-tight text-primary transition-transform active:scale-95"
            >
              MarkHub
            </button>
            <nav className="hidden items-center gap-6 md:flex">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onNavigate(item.id)}
                  className={`pb-1 text-label-md font-medium transition-colors active:scale-95 ${
                    activeTab === item.id
                      ? 'border-b-2 border-primary font-bold text-primary'
                      : 'text-on-surface-variant hover:text-primary'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative hidden lg:block">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
              <input
                className="h-10 w-72 rounded-full border border-outline-variant/50 bg-surface-container py-2 pl-9 pr-4 text-label-md text-on-surface outline-none transition-colors placeholder:text-on-surface-variant focus:border-primary"
                placeholder="搜索项目、数据集或提示词"
                type="search"
              />
            </div>
            <button
              type="button"
              className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary active:scale-95"
              aria-label="通知"
            >
              <Bell className="h-5 w-5" />
            </button>
            <button
              type="button"
              className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary active:scale-95"
              aria-label="账户"
            >
              <UserCircle className="h-6 w-6" />
            </button>
          </div>
        </div>
      </header>

      <main className="relative z-10 min-h-[calc(100vh-4rem)] w-full overflow-hidden">
        {children}
      </main>
    </div>
  );
}

