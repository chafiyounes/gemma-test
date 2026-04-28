import { useState } from "react";
import "./AuthScreen.css";

export default function AuthScreen({ onLogin, loading, error }) {
  const [password, setPassword] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!password.trim() || loading) {
      return;
    }
    await onLogin(password);
  };

  return (
    <div className="auth-shell">
      <div className="auth-aurora auth-aurora-one" />
      <div className="auth-aurora auth-aurora-two" />
      <section className="auth-card">
        <div className="auth-kicker">Acces protege</div>
        <h1>Darija Chatbot</h1>
        <p className="auth-copy">
          Entrez le mot de passe partage pour acceder a l&apos;assistant client.
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
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

          <button className="auth-submit" type="submit" disabled={!password.trim() || loading}>
            {loading ? "Connexion..." : "Entrer"}
          </button>
        </form>
      </section>
    </div>
  );
}