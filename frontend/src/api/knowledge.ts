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
  permissions: PermissionEntry[];
}

export interface ImportTaskResponse {
  task_id: string;
  accepted_count?: number;
  accepted?: number;
  rejected: Array<{ filename: string; reason: string }>;
}

export interface KnowledgeIndexStatus {
  unit_id: number;
  configured: boolean;
  db_status: string;
  chunk_count: number | null;
  consistent: boolean;
  detail: string;
}

export async function importFiles(files: File[]): Promise<ImportTaskResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
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

export async function patchKnowledgeUnit(
  id: number,
  input: UnitPatchInput,
): Promise<KnowledgeUnitItem> {
  const { data } = await http.patch<KnowledgeUnitItem>(`/knowledge-units/${id}`, input);
  return data;
}

export async function batchDeleteUnits(ids: number[]): Promise<void> {
  await http.delete("/knowledge-units", { data: { ids } });
}

export async function configureUnitPermissions(
  id: number,
  permissions: Array<{
    target_type: PermissionEntry["target_type"];
    target_id: number | null;
  }>,
): Promise<PermissionEntry[]> {
  const { data } = await http.post<PermissionEntry[]>(
    `/knowledge-units/${id}/permissions`,
    { permissions },
  );
  return data;
}

export async function checkPermissions(
  user_id: number,
  unit_ids: number[],
): Promise<{ authorized_unit_ids: number[]; unauthorized_unit_ids: number[] }> {
  const { data } = await http.post("/knowledge/check-permissions", { user_id, unit_ids });
  return data;
}

export async function getKnowledgeIndexStatus(id: number): Promise<KnowledgeIndexStatus> {
  const { data } = await http.get<KnowledgeIndexStatus>(
    `/knowledge-units/${id}/index-status`,
  );
  return data;
}

export async function reindexKnowledgeUnit(id: number): Promise<KnowledgeIndexStatus> {
  const { data } = await http.post<KnowledgeIndexStatus>(
    `/knowledge-units/${id}/reindex`,
  );
  return data;
}
