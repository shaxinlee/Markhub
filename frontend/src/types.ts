/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface Project {
  id: string;
  backendJobId?: string;
  name: string;
  type: 'CV' | 'Multimodal' | 'Keypoints' | 'NLP';
  progress: number;
  thumbnail: string;
  description: string;
  totalImages: number;
  totalAnnotations: number;
  category: string;
  images: string[];
  model?: string;
  status?: string;
  updatedAt?: number;
  promptTemplateName?: string;
  errorCount?: number;
}

export interface BackendJobSummary {
  dataset_id?: string;
  job_id: string;
  filename: string;
  model?: string;
  model_dir?: string;
  status: string;
  page_count: number;
  completed_pages: number;
  block_count: number;
  error_count?: number;
  first_page_url?: string;
  updated_at?: number;
  prompt_template?: {
    id?: string;
    name?: string;
  };
  annotation_status?: 'none' | 'first_annotated' | 'second_annotating' | 'second_annotated';
  convert_status?: 'none' | 'converting' | 'success' | 'failed' | 'partial_success';
  convert_error?: string;
  converted_formats?: string[];
  first_annotated_at?: number | null;
  second_annotated_at?: number | null;
  last_convert_record?: {
    task_id?: string;
    target_format?: string;
    status?: string;
    output_path?: string;
    created_at?: string;
    error?: string;
    skipped_samples?: number;
  } | null;
}

export type AnnotationFeature = 'bounding_box' | 'polygon' | 'layout' | 'keypoints' | 'text_transcription';

export interface PromptTemplateOption {
  id: string;
  name: string;
  category: AnnotationFeature;
  prompt?: string;
}

export type PromptType =
  | 'data_annotation'
  | 'second_review'
  | 'data_cleaning'
  | 'data_conversion'
  | 'model_inference'
  | 'system_role'
  | 'custom';

export type PromptTaskType =
  | 'layout_analysis'
  | 'weak_heading_detection'
  | 'table_recognition'
  | 'image_captioning'
  | 'data_quality_check'
  | 'llamafactory_conversion'
  | 'swift_conversion'
  | 'second_manual_review'
  | 'auto_annotation'
  | 'custom';

export interface PromptVersion {
  id: string;
  prompt_template_id: string;
  version: string;
  content: string;
  variables: string | Record<string, unknown> | unknown[];
  default_values: Record<string, unknown>;
  change_log?: string;
  created_by?: string;
  created_at?: string;
}

export interface PromptRecord {
  id: string;
  name: string;
  description: string;
  type: PromptType;
  task_type: PromptTaskType;
  model_name: string;
  content: string;
  variables: string | Record<string, unknown> | unknown[];
  default_values: Record<string, unknown>;
  version: string;
  status: 'enabled' | 'disabled';
  is_default: boolean;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  deleted_at?: string | null;
  notes?: string;
  usage_scenarios?: string[];
  versions?: PromptVersion[];
}

export interface PromptTestResult {
  success: boolean;
  inputs: Record<string, unknown>;
  rendered_prompt: string;
  model_output: string;
  model_name: string;
  elapsed_ms: number;
  token_usage?: Record<string, unknown> | null;
  error?: string;
}

export type BackendBlockType =
  | 'doc_title'
  | 'paragraph_title'
  | 'text'
  | 'table_of_contents'
  | 'table'
  | 'formula'
  | 'chart'
  | 'figure_title'
  | 'image'
  | 'vision_footnote'
  | 'header'
  | 'footer'
  | 'caption'
  | 'handwriting'
  | 'seal';

export interface AnnotationSegment {
  id: string;
  type: BackendBlockType;
  box: [number, number, number, number]; // [top, left, width, height] in percentage (0 to 100)
  text: string;
  confidence: number;
  pageId?: number;
  level?: 'H1' | 'H2' | 'H3' | null;
  weakHeading?: boolean;
  bbox?: [number, number, number, number];
}

export interface Collaborator {
  id: string;
  name: string;
  role: string;
  avatar: string;
  active: boolean;
}

export interface AnnotationStats {
  totalImages: number;
  totalAnnotations: string; // e.g., "3.1M"
  activeCollaborators: number;
}
