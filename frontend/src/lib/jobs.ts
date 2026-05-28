/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { AnnotationFeature, BackendJobSummary, Project, PromptTemplateOption } from '../types';

export function mapJobToProject(job: BackendJobSummary): Project {
  const progress = job.page_count > 0 ? Math.round(((job.completed_pages || 0) / job.page_count) * 100) : 0;
  const thumbnail = job.first_page_url || '';

  return {
    id: job.job_id,
    backendJobId: job.job_id,
    name: job.filename || `Dataset ${job.job_id}`,
    type: 'CV',
    progress,
    thumbnail,
    description: `${job.page_count || 0} pages · ${job.block_count || 0} layout blocks · ${job.model || 'Unknown model'}`,
    totalImages: job.page_count || 0,
    totalAnnotations: job.block_count || 0,
    category: 'PDF Layout Analysis',
    images: thumbnail ? [thumbnail] : [],
    model: job.model || 'Unknown model',
    status: job.status,
    updatedAt: job.updated_at,
    promptTemplateName: job.prompt_template?.name,
    errorCount: job.error_count || 0,
  };
}

export function createLayoutDraftProject(): Project {
  return {
    id: `layout_draft_${Date.now()}`,
    name: 'Layout Analysis Workspace',
    type: 'CV',
    progress: 0,
    thumbnail: '',
    description: 'Upload a PDF document to start backend layout analysis.',
    totalImages: 0,
    totalAnnotations: 0,
    category: 'PDF Layout Analysis',
    images: [],
  };
}

export function normalizePromptTemplates(items: unknown[]): PromptTemplateOption[] {
  return items
    .filter((item): item is Partial<PromptTemplateOption> => Boolean(item) && typeof item === 'object')
    .map((item) => ({
      id: String(item.id || 'default_template_1'),
      name: String(item.name || '默认模板 1'),
      category: (item.category || 'layout') as AnnotationFeature,
      prompt: typeof item.prompt === 'string' ? item.prompt : '',
    }));
}

export function isCompleteBackendJob(status: string): boolean {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'complete' || normalized === 'completed' || normalized === 'done';
}

export function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}
