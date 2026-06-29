import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import { ConfirmProvider } from "./context/ConfirmContext";
import ErrorBoundary from "./components/ErrorBoundary";
import { LoadingSpinner } from "./components/ui";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

// ── Route-level code splitting ──────────────────────────────────────────────
const Landing = lazy(() => import("./pages/Landing"));
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Upload = lazy(() => import("./pages/Upload"));
const Analysis = lazy(() => import("./pages/Analysis"));
const Report = lazy(() => import("./pages/Report"));
const Admin = lazy(() => import("./pages/Admin"));
const History = lazy(() => import("./pages/History"));
const NotFound = lazy(() => import("./pages/NotFound"));

const PageFallback = () => (
  <LoadingSpinner text="页面加载中..." className="py-24" />
);

// ── QueryClient with sensible defaults ──────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,       // 1 min before refetch
      gcTime: 300_000,         // 5 min garbage collection
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>
          <ConfirmProvider>
            <BrowserRouter>
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <Routes>
                    <Route element={<Layout />}>
                      <Route path="/admin-7c2b9e" element={<Admin />} />
                      <Route path="/" element={<Landing />} />
                      <Route path="/login" element={<Login />} />
                      <Route path="/register" element={<Register />} />
                      <Route
                        path="/upload"
                        element={
                          <ProtectedRoute>
                            <Upload />
                          </ProtectedRoute>
                        }
                      />
                      <Route
                        path="/analysis"
                        element={<Navigate to="/history" replace />}
                      />
                      <Route
                        path="/analysis/:id"
                        element={
                          <ProtectedRoute>
                            <Analysis />
                          </ProtectedRoute>
                        }
                      />
                      <Route
                        path="/report"
                        element={<Navigate to="/history" replace />}
                      />
                      <Route
                        path="/report/:id"
                        element={
                          <ProtectedRoute>
                            <Report />
                          </ProtectedRoute>
                        }
                      />
                      <Route
                        path="/history"
                        element={
                          <ProtectedRoute>
                            <History />
                          </ProtectedRoute>
                        }
                      />
                      <Route path="*" element={<NotFound />} />
                    </Route>
                  </Routes>
                </Suspense>
              </ErrorBoundary>
            </BrowserRouter>
          </ConfirmProvider>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
