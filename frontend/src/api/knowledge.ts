import { http, type PageData, type ListQuery } from "./client";

export interface KnowledgeUnitItem {
  id: number;
  unit_code: string;
  title: string;
  summary: string | null;
  category: string | null;
  file_type: string | null;
  source_file_name: string | null;
  permissions_summary: string;
  creator_id: number;
  creator_name: string;
  status: "active" | "vector_pending" | "failed";
  created_at: string;
  updated_at: string;
}

export interface PermissionEntry {
  target_type: "global" | "department" | "role" | "user";
  target_id: number | null;
  target_label: string;
}

export interface KnowledgeUnitDetail extends KnowledgeUnitItem {
  content: string;
  tags: string[];
  attachments: Array<{
    id: number;
    file_name: string;
    file_size: number;
    content_type: string;
    download_url: string;
  }>;
  permissions: PermissionEntry[];
}

export interface ImportTaskResponse {
  task_id: string;
  accepted_count?: number;
  accepted?: number;
  rejected: Array<{ filename: string; reason: string }>;
}

export async function importFiles(files: File[]): Promise<ImportTaskResponse> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const { data } = await http.post<ImportTaskResponse>("/knowledge/import", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120_000,
  });
  return data;
}

export async function getKnowledgeUnits(
  params: ListQuery,
): Promise<PageData<KnowledgeUnitItem>> {
  const { data } = await http.get<PageData<KnowledgeUnitItem>>("/knowledge-units", { params });
  return data;
}

export async function getKnowledgeUnit(id: number): Promise<KnowledgeUnitDetail> {
  const { data } = await http.get<KnowledgeUnitDetail>(`/knowledge-units/${id}`);
  return data;
}

export interface UnitPatchInput {
  title?: string;
  content?: string;
  summary?: string;
  category?: string;
  tags?: string[];
}

export async function patchKnowledgeUnit(id: number, input: UnitPatchInput): Promise<KnowledgeUnitDetail> {
  const { data } = await http.patch<KnowledgeUnitDetail>(`/knowledge-units/${id}`, input);
  return data;
}

/** 批量删除：ids 上限按接口约定文档 §7.3 取 1–100（M3 spec 写 200，文档矛盾从严控制） */
export async function batchDeleteUnits(ids: number[]): Promise<{
  succeeded: number[];
  failed: Array<{ id: number; error_code: string }>;
}> {
  const { data } = await http.delete("/knowledge-units", { data: { ids } });
  return data;
}

export async function configureUnitPermissions(
  id: number,
  permissions: Array<{ target_type: PermissionEntry["target_type"]; target_id: number | null }>,
): Promise<void> {
  await http.post(`/knowledge-units/${id}/permissions`, { permissions });
}

export async function checkPermissions(
  user_id: number,
  unit_ids: number[],
): Promise<{ authorized_unit_ids: number[]; unauthorized_unit_ids: number[] }> {
  const { data } = await http.post("/knowledge/check-permissions", { user_id, unit_ids });
  return data;
}
