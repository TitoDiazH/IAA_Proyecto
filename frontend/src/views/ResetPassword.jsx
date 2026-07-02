import { BookOpen } from "lucide-react";
import { useState } from "react";
import { isPasswordValid, PasswordRequirements } from "../passwordRules";
import { supabase } from "../supabase";
const campusImage = "/campus.webp";

export default function ResetPassword({ onDone }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (!isPasswordValid(password)) {
      setError("La contraseña no cumple los requisitos de seguridad.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    setLoading(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      onDone?.();
    } catch (err) {
      setError(err.message || "No se pudo actualizar la contraseña.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page" style={{ backgroundImage: `url(${campusImage})` }}>
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo" aria-hidden="true">
            <BookOpen size={22} />
          </div>
          <h1 className="auth-title">Nueva contraseña</h1>
          <span className="auth-subtitle">Universidad de los Andes</span>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="form-field">
            <label htmlFor="reset-password" className="form-label">
              Nueva contraseña
            </label>
            <input
              id="reset-password"
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              minLength={8}
              disabled={loading}
            />
            <PasswordRequirements password={password} />
          </div>

          <div className="form-field">
            <label htmlFor="reset-password-confirm" className="form-label">
              Confirmar contraseña
            </label>
            <input
              id="reset-password-confirm"
              type="password"
              className="form-input"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              disabled={loading}
            />
          </div>

          {error && <p className="message error">{error}</p>}

          <button
            type="submit"
            className="primary-button auth-submit"
            disabled={loading || !isPasswordValid(password) || password !== confirmPassword}
          >
            {loading ? "Guardando…" : "Guardar nueva contraseña"}
          </button>
        </form>
      </div>
    </div>
  );
}
