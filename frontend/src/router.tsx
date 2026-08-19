import {lazy, Suspense} from "react";
import {createBrowserRouter, Navigate} from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";
import {RequireAuth} from "@/components/layout/RequireAuth";
import {PageLoading} from "@/components/shared/PageStates";
import LoginPage from "@/pages/LoginPage";

const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const KnowledgeUnitsPage = lazy(() => import("@/pages/KnowledgeUnitsPage"));
const ChatPage = lazy(() => import("@/pages/ChatPage"));
const UsersPage = lazy(() => import("@/pages/UsersPage"));
const RolesPage = lazy(() => import("@/pages/RolesPage"));
const DepartmentsPage = lazy(() => import("@/pages/DepartmentsPage"));
const ImportPage = lazy(() => import("@/pages/ImportPage"));
const FaqsPage = lazy(() => import("@/pages/FaqsPage"));
const GapsPage = lazy(() => import("@/pages/GapsPage"));
const ProfilePage = lazy(() => import("@/pages/ProfilePage"));

function lazyEl(node: React.ReactNode) {
  return <Suspense fallback={<PageLoading />}>{node}</Suspense>;
}

export const router = createBrowserRouter([
  {path: "/login", element: <LoginPage />},
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      {index: true, element: lazyEl(<DashboardPage />)},
      {path: "users", element: lazyEl(<UsersPage />)},
      {path: "roles", element: lazyEl(<RolesPage />)},
      {path: "departments", element: lazyEl(<DepartmentsPage />)},
      {path: "knowledge/import", element: lazyEl(<ImportPage />)},
      {path: "knowledge/units", element: lazyEl(<KnowledgeUnitsPage />)},
      {path: "chat", element: lazyEl(<ChatPage />)},
      {path: "faqs", element: lazyEl(<FaqsPage />)},
      {path: "gaps", element: lazyEl(<GapsPage />)},
      {path: "profile", element: lazyEl(<ProfilePage />)},
    ],
  },
  {path: "*", element: <Navigate to="/" replace />},
]);
