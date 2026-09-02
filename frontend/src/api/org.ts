import { http, type PageData } from "./client";

export interface DepartmentNode {
  id: number;
  name: string;
  parent_id: number | null;
  leader_id: number | null;
  sort_order: number;
  member_count: number;
  children: DepartmentNode[];
}

export interface DepartmentInput {
  name: string;
  parent_id: number | null;
  leader_id: number | null;
  sort_order: number;
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

export interface UserListQuery {
  page?: number;
  page_size?: number;
  keyword?: string;
  department_id?: number;
  status?: 0 | 1;
}

export async function getDepartments(): Promise<DepartmentNode[]> {
  const { data } = await http.get<DepartmentNode[]>("/org/departments");
  return data;
}

export async function createDepartment(input: DepartmentInput): Promise<DepartmentNode> {
  const { data } = await http.post<DepartmentNode>("/org/departments", input);
  return data;
}

export async function updateDepartment(
  id: number,
  input: DepartmentInput,
): Promise<DepartmentNode> {
  const { data } = await http.put<DepartmentNode>("/org/departments/" + id, input);
  return data;
}

export async function deleteDepartment(id: number): Promise<void> {
  await http.delete("/org/departments/" + id);
}

export async function getUsers(params: UserListQuery): Promise<PageData<UserItem>> {
  const { data } = await http.get<PageData<UserItem>>("/org/users", { params });
  return data;
}

export async function getUser(id: number): Promise<UserItem> {
  const { data } = await http.get<UserItem>("/org/users/" + id);
  return data;
}

export interface UserCreateInput {
  username: string;
  password: string;
  display_name: string;
  department_id: number;
  role_ids: number[];
}

export interface UserUpdateInput {
  display_name?: string;
  department_id?: number;
  role_ids?: number[];
  status?: 0 | 1;
}

export async function createUser(input: UserCreateInput): Promise<UserItem> {
  const { data } = await http.post<UserItem>("/org/users", input);
  return data;
}

export async function updateUser(id: number, input: UserUpdateInput): Promise<UserItem> {
  const { data } = await http.put<UserItem>("/org/users/" + id, input);
  return data;
}

export async function patchUserStatus(id: number, status: 0 | 1): Promise<void> {
  await http.patch("/org/users/" + id + "/status", { status });
}

export async function resetPassword(id: number, new_password: string): Promise<void> {
  await http.post("/org/users/" + id + "/reset-password", { new_password });
}

export async function getRoles(): Promise<RoleItem[]> {
  const { data } = await http.get<RoleItem[]>("/org/roles");
  return data;
}

export async function assignRolePermissions(
  roleId: number,
  permission_codes: string[],
): Promise<void> {
  await http.post("/org/roles/" + roleId + "/permissions", { permission_codes });
}

export async function getPermissionCodes(): Promise<string[]> {
  const { data } = await http.get<string[]>("/org/permissions");
  return data;
}
