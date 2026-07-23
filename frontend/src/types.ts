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
  annotation_type?: 'layout' | 'bounding_box';
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
  | 'flowchart'
  | 'diagram'
  | 'image'
  | 'vision_footnote'
  | 'header'
  | 'footer'
  | 'caption'
  | 'handwriting'
  | 'seal';

export interface BackendBlock {
  id: string;
  text?: string;
  bbox: [number, number, number, number];
  page_id: number;
  block_type: BackendBlockType;
  description?: string;
  chart_description?: string;
  level?: 'H1' | 'H2' | 'H3' | 'H4' | null;
}

export interface BackendPage {
  page_id: number;
  image_url: string;
  width: number;
  height: number;
  status?: string;
  blocks?: BackendBlock[];
  error?: string;
  elapsed_time?: number;
}

export interface BackendJob {
  job_id: string;
  filename: string;
  status: string;
  page_count: number;
  completed_pages: number;
  pages: BackendPage[];
  result?: { blocks?: BackendBlock[]; [key: string]: unknown };
  warnings?: string[];
  errors?: string[];
  config?: { model?: string; base_url?: string; timeout?: string; max_tokens?: string; model_dir?: string };
  resize?: { preset?: string; image_profile?: string; width?: number; height?: number };
  prompt_template?: { id?: string; name?: string };
}

export interface BackendConfig {
  base_url?: string;
  model?: string;
  has_api_key?: string;
  render_dpi?: string;
  max_pages?: string;
  max_pdf_bytes?: string;
  qwen_preset?: string;
  qwen_image_profile?: string;
  qwen_width?: string;
  qwen_height?: string;
  prompt_template_id?: string;
  timeout?: string;
  max_tokens?: string;
}

export interface AnnotationSegment {
  id: string;
  type: BackendBlockType;
  box: [number, number, number, number]; // [top, left, width, height] in percentage (0 to 100)
  text: string;
  chartDescription?: string;
  confidence: number;
  pageId?: number;
  level?: 'H1' | 'H2' | 'H3' | 'H4' | null;
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

export interface BoundingBoxLabel {
  id: string;
  name: string;
  color: string;
  description?: string;
}

export interface BoundingBoxAnnotation {
  id: string;
  image_id: string;
  label_id: string;
  label_name: string;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2] in percentage (0 to 100)
  confidence?: number;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface BoundingBoxImage {
  id: string;
  dataset_id: string;
  filename: string;
  image_url: string;
  width: number;
  height: number;
  annotation_count: number;
  status: 'pending' | 'annotated' | 'reviewed';
  created_at: string;
}

export interface BoundingBoxDataset {
  id: string;
  name: string;
  description?: string;
  image_count: number;
  annotated_count: number;
  label_count: number;
  status: 'active' | 'archived' | 'completed';
  created_at: string;
  updated_at: string;
}

export interface BoundingBoxJob {
  dataset_id: string;
  dataset_name: string;
  status: 'draft' | 'annotating' | 'completed' | 'failed';
  image_count: number;
  annotated_count: number;
  labels: BoundingBoxLabel[];
  images: BoundingBoxImage[];
  annotations: Record<string, BoundingBoxAnnotation[]>;
  created_at: string;
  updated_at: string;
}
