import { useEffect, useState } from "react";
import { ChatProvider } from "./context/ChatContext";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import AuthScreen from "./components/AuthScreen";
import { getSession, login, logout } from "./services/api";

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [session, setSession] = useState(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const loadSession = async () => {
      try {
        const currentSession = await getSession();
        if (!cancelled) {
          setSession(currentSession.authenticated ? currentSession : null);
        }
      } catch {
        if (!cancelled) {
          setSession(null);
        }
      } finally {
        if (!cancelled) {
          setLoadingSession(false);
        }
      }
    };

    loadSession();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogin = async (password) => {
    setAuthBusy(true);
    setAuthError("");
    try {
      const nextSession = await login(password);
      setSession(nextSession);
    } catch (error) {
      setAuthError(error.message || "Connexion impossible");
    } finally {
      setAuthBusy(false);
    }
  };

  const handleLogout = async () => {
    setSidebarOpen(false);
    try {
      await logout();
    } finally {
      localStorage.removeItem("sendbot_state");
      setSession(null);
    }
  };

  if (loadingSession) {
    return <AuthScreen onLogin={async () => {}} loading error="" />;
  }

  if (!session?.authenticated) {
    return <AuthScreen onLogin={handleLogin} loading={authBusy} error={authError} />;
  }

  return (
    <ChatProvider>
      <div className="app-layout">
        <Sidebar
          isOpen={sidebarOpen}
          session={session}
          onLogout={handleLogout}
          onClose={() => setSidebarOpen(false)}
        />
        <ChatArea
          session={session}
          onOpenSidebar={() => setSidebarOpen(true)}
          onLogout={handleLogout}
        />
      </div>
    </ChatProvider>
  );
}
