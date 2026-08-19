import { http, type PageData, type ListQuery } from "./client";
import type { PermissionEntry } from "./knowledge";

export interface FaqItem {
  id: number;
  question: string;
  answer: string;
  category: string | null;
  related_unit_id: number | null;
  related_unit_code: string | null;
  source_type: "manual" | "auto_mined";
  status: "pending_review" | "published" | "rejected";
  hit_count: number;
  reviewer_id: number | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GapItem {
  id: number;
  question_pattern: string;
  sample_questions: string[];
  ask_count: number;
  last_asked_at: string;
  status: "unresolved" | "resolved" | "ignored";
  resolved_unit_id: number | null;
}

export async function getFaqs(params: ListQuery): Promise<PageData<FaqItem>> {
  const { data } = await http.get<PageData<FaqItem>>("/faqs", { params });
  return data;
}

export async function getFaqRecommendations(): Promise<FaqItem[]> {
  const { data } = await http.get<FaqItem[]>("/faqs/recommendations");
  return data;
}

export interface FaqCreateInput {
  question: string;
  answer: string;
  category?: string | null;
  related_unit_id?: number | null;
}

export async function createFaq(input: FaqCreateInput): Promise<FaqItem> {
  const { data } = await http.post<FaqItem>("/faqs", input);
  return data;
}

export async function patchFaq(id: number, input: Partial<FaqCreateInput>): Promise<FaqItem> {
  const { data } = await http.patch<FaqItem>(`/faqs/${id}`, input);
  return data;
}

export async function reviewFaq(
  id: number,
  action: "approve" | "reject",
  editedAnswer?: string,
): Promise<FaqItem> {
  const { data } = await http.post<FaqItem>(`/faqs/${id}/review`, {
    action,
    edited_answer: action === "approve" ? (editedAnswer ?? null) : null,
  });
  return data;
}

export async function offlineFaq(id: number): Promise<void> {
  await http.delete(`/faqs/${id}`);
}

export async function getGaps(params: ListQuery): Promise<PageData<GapItem>> {
  const { data } = await http.get<PageData<GapItem>>("/knowledge-gaps", { params });
  return data;
}

export interface CreateUnitFromGapInput {
  title: string;
  content: string;
  category?: string | null;
  permissions: Array<{ target_type: PermissionEntry["target_type"]; target_id: number | null }>;
}

export async function createUnitFromGap(id: number, input: CreateUnitFromGapInput): Promise<void> {
  await http.post(`/knowledge-gaps/${id}/create-unit`, input);
}
