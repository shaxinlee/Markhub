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

export type BackendBlockType =
  | 'doc_title'
  | 'paragraph_title'
  | 'text'
  | 'table'
  | 'figure_title'
  | 'image'
  | 'vision_footnote'
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
