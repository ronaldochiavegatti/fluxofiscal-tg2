import { createContext, useContext } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { TokensProvider } from "./TokensContext";
import { type DemoUser, type DocumentEntry } from "./types";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { UploadPage } from "./pages/UploadPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { AgentPage } from "./pages/AgentPage";
import { ConfiguracoesPage } from "./pages/ConfiguracoesPage";

type DocsCtx = {
  docs: DocumentEntry[];
  addDoc: (doc: DocumentEntry) => void;
  updateDoc: (id: string, patch: Partial<DocumentEntry>) => void;
  removeDoc: (id: string) => void;
  clearDocs: () => void;
};

const DocumentsContext = createContext<DocsCtx | null>(null);

export function useDocuments() {
  const ctx = useContext(DocumentsContext);
  if (!ctx) throw new Error("DocumentsContext not found");
  return ctx;
}

type GuardProps = {
  user: DemoUser | null;
  children: React.ReactNode;
};

function ProtectedRoute({ user, children }: GuardProps) {
  if (!user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  const [user, setUser] = useLocalStorage<DemoUser | null>("demo-user", null);
  const [docs, setDocs] = useLocalStorage<DocumentEntry[]>("demo-documents", []);
  const navigate = useNavigate();

  const addDoc = (doc: DocumentEntry) => {
    setDocs((prev) => [doc, ...prev]);
  };

  const updateDoc = (id: string, patch: Partial<DocumentEntry>) => {
    setDocs((prev) => prev.map((d) => (d.id === id ? { ...d, ...patch } : d)));
  };

  const removeDoc = (id: string) => {
    setDocs((prev) => prev.filter((d) => d.id !== id));
  };

  const clearDocs = () => {
    setDocs([]);
  };

  return (
    <DocumentsContext.Provider value={{ docs, addDoc, updateDoc, removeDoc, clearDocs }}>
      <Routes>
        <Route
          path="/"
          element={<LoginPage onEnter={(u) => { setUser(u); navigate("/dashboard"); }} />}
        />
        <Route
          path="/*"
          element={
            <ProtectedRoute user={user}>
              <TokensProvider email={user?.email || ""}>
                <Layout userEmail={user?.email}>
                  <Routes>
                    <Route path="dashboard" element={<DashboardPage user={user!} />} />
                    <Route path="upload" element={<UploadPage user={user!} />} />
                    <Route path="documents" element={<DocumentsPage />} />
                    <Route path="documents/:id" element={<DocumentDetailPage />} />
                    <Route path="chat" element={<AgentPage user={user!} />} />
                    <Route path="configuracoes" element={<ConfiguracoesPage user={user!} />} />
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                  </Routes>
                </Layout>
              </TokensProvider>
            </ProtectedRoute>
          }
        />
      </Routes>
    </DocumentsContext.Provider>
  );
}
