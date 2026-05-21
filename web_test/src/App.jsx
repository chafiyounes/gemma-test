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

  const handleLogin = async (credentials) => {
    setAuthBusy(true);
    setAuthError("");
    try {
      const nextSession = await login(credentials);
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
    return (
      <div className="sendbot-theme-island">
        <div className="session-boot">Chargement...</div>
      </div>
    );
  }

  if (!session?.authenticated) {
    return (
      <div className="sendbot-theme-island">
        <AuthScreen onLogin={handleLogin} loading={authBusy} error={authError} />
      </div>
    );
  }

  return (
    <div className="sendbot-theme-island">
    <ChatProvider session={session}>
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
    </div>
  );
}
