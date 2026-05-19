import { useState } from "react";
import ThemeToggle from "./ThemeToggle";
import "./AuthScreen.css";

export default function AuthScreen({ onLogin, loading, error }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!username.trim() || !password.trim() || loading) {
      return;
    }
    await onLogin({ username: username.trim(), password });
  };

  return (
    <div className="auth-shell">
      <ThemeToggle className="theme-toggle--auth" />
      <div className="auth-aurora auth-aurora-one" />
      <div className="auth-aurora auth-aurora-two" />
      <section className="auth-card">
        <div className="auth-kicker">Acces protege</div>
        <h1>Darija Chatbot</h1>
        <p className="auth-copy">
          Connectez-vous avec votre identifiant et mot de passe.
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-label" htmlFor="site-username">
            Identifiant
          </label>
          <input
            id="site-username"
            className="auth-input"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="Nom d&apos;utilisateur"
          />
          <label className="auth-label" htmlFor="site-password">
            Mot de passe
          </label>
          <input
            id="site-password"
            className="auth-input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Saisissez le mot de passe"
          />

          {error ? <div className="auth-error">{error}</div> : null}

          <button
            className="auth-submit"
            type="submit"
            disabled={!username.trim() || !password.trim() || loading}
          >
            {loading ? "Connexion..." : "Entrer"}
          </button>
        </form>
      </section>
    </div>
  );
}