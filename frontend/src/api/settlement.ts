import { http, type PageData } from "./client";

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
  sample_questions_json: string[];
  ask_count: number;
  last_asked_at: string;
  status: "unresolved" | "resolved" | "ignored";
  resolved_unit_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface FaqListQuery {
  page?: number;
  page_size?: number;
  status?: FaqItem["status"];
  source_type?: FaqItem["source_type"];
}

export async function getFaqs(params: FaqListQuery): Promise<PageData<FaqItem>> {
  const { data } = await http.get<PageData<FaqItem>>("/faqs", { params });
  return data;
}

export async function getFaqRecommendations(
  page = 1,
  page_size = 20,
): Promise<PageData<FaqItem>> {
  const { data } = await http.get<PageData<FaqItem>>("/faqs/recommendations", {
    params: { page, page_size },
  });
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

export async function reviewFaq(
  id: number,
  action: "approve" | "reject",
  editedAnswer?: string,
): Promise<FaqItem> {
  const { data } = await http.post<FaqItem>("/faqs/" + id + "/review", {
    action,
    edited_answer: action === "approve" ? (editedAnswer ?? null) : null,
  });
  return data;
}

export async function offlineFaq(id: number): Promise<void> {
  await http.delete("/faqs/" + id);
}

export interface GapListQuery {
  page?: number;
  page_size?: number;
  status?: GapItem["status"];
}

export async function getGaps(params: GapListQuery): Promise<PageData<GapItem>> {
  const { data } = await http.get<PageData<GapItem>>("/knowledge-gaps", { params });
  return data;
}

export interface CreateUnitFromGapInput {
  title: string;
  category?: string | null;
  summary?: string | null;
  content?: string | null;
}

export async function createUnitFromGap(
  id: number,
  input: CreateUnitFromGapInput,
): Promise<{ gap_id: number; unit_id: number }> {
  const { data } = await http.post<{ gap_id: number; unit_id: number }>(
    "/knowledge-gaps/" + id + "/create-unit",
    input,
  );
  return data;
}
