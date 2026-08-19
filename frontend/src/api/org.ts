import { http, type PageData, type ListQuery } from "./client";

export interface DepartmentNode {
  id: number;
  name: string;
  parent_id: number | null;
  leader_id: number | null;
  member_count: number;
  children: DepartmentNode[];
}

export interface UserItem {
  id: number;
  username: string;
  display_name: string;
  department_id: number;
  department_name: string;
  role_codes: string[];
  status: number;
  created_at: string;
  updated_at: string;
}

export interface RoleItem {
  id: number;
  role_name: string;
  role_code: string;
  description: string | null;
  permissions: string[];
}

export async function getDepartments(): Promise<DepartmentNode[]> {
  const { data } = await http.get<DepartmentNode[]>("/org/departments");
  return data;
}

export async function getUsers(params: ListQuery & { department_id?: number }): Promise<PageData<UserItem>> {
  const { data } = await http.get<PageData<UserItem>>("/org/users", { params });
  return data;
}

export async function getUser(id: number): Promise<UserItem> {
  const { data } = await http.get<UserItem>(`/org/users/${id}`);
  return data;
}

export interface UserCreateInput {
  username: string;
  password: string;
  display_name: string;
  department_id: number;
  role_ids: number[];
}

export async function createUser(input: UserCreateInput): Promise<UserItem> {
  const { data } = await http.post<UserItem>("/org/users", input);
  return data;
}

export async function patchUserStatus(id: number, status: 0 | 1): Promise<void> {
  await http.patch(`/org/users/${id}/status`, { status });
}

export async function resetPassword(id: number, new_password: string): Promise<void> {
  await http.post(`/org/users/${id}/reset-password`, { new_password });
}

export async function getRoles(): Promise<RoleItem[]> {
  const { data } = await http.get<RoleItem[]>("/org/roles");
  return data;
}

export async function assignRolePermissions(
  roleId: number,
  permission_codes: string[],
  permission_type: "menu" | "button" | "api" = "menu",
): Promise<void> {
  await http.post(`/org/roles/${roleId}/permissions`, { permission_codes, permission_type });
}

export async function getPermissionDict(): Promise<Array<{ code: string; description: string }>> {
  const { data } = await http.get("/org/permissions");
  return data;
}
