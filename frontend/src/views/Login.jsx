import { BookOpen } from "lucide-react";
import { useState } from "react";
import { isPasswordValid, PasswordRequirements } from "../passwordRules";
import { supabase } from "../supabase";
const campusImage = "/campus.webp";

const ERROR_MAP = {
  "Invalid login credentials": "Correo o contraseña incorrectos.",
  "Email not confirmed": "Debes confirmar tu correo antes de ingresar.",
  "User already registered": "Ya existe una cuenta con este correo.",
  "Password should be at least": "La contraseña debe tener al menos 8 caracteres.",
  "For security purposes": "Demasiados intentos. Espera unos minutos antes de reintentar.",
};

function translateError(msg) {
  for (const [key, value] of Object.entries(ERROR_MAP)) {
    if (msg.includes(key)) return value;
  }
  return msg;
}

export default function Login() {
  const [mode, setMode] = useState("login"); // "login" | "register" | "forgot"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      if (mode === "login") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      } else if (mode === "register") {
        if (!isPasswordValid(password)) {
          setError("La contraseña no cumple los requisitos de seguridad.");
          setLoading(false);
          return;
        }
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setSuccess(
          "Cuenta creada. Revisa tu correo y confirma tu cuenta antes de ingresar."
        );
        setMode("login");
        setPassword("");
      } else {
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: window.location.origin,
        });
        if (error) throw error;
        setSuccess(
          "Si existe una cuenta con ese correo, te enviamos un link para restablecer tu contraseña."
        );
      }
    } catch (err) {
      setError(translateError(err.message || "Error inesperado"));
    } finally {
      setLoading(false);
    }
  }

  function toggleMode() {
    setMode((m) => (m === "login" ? "register" : "login"));
    setError(null);
    setSuccess(null);
    setPassword("");
  }

  function goToForgotPassword() {
    setMode("forgot");
    setError(null);
    setSuccess(null);
    setPassword("");
  }

  function backToLogin() {
    setMode("login");
    setError(null);
    setSuccess(null);
    setPassword("");
  }

  return (
    <div className="auth-page" style={{ backgroundImage: `url(${campusImage})` }}>
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo" aria-hidden="true">
            <BookOpen size={22} />
          </div>
          <h1 className="auth-title">Revisor de Syllabus</h1>
          <span className="auth-subtitle">Universidad de los Andes</span>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="form-field">
            <label htmlFor="auth-email" className="form-label">
              Correo electrónico
            </label>
            <input
              id="auth-email"
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="usuario@miuandes.cl"
              disabled={loading}
            />
          </div>

          {mode !== "forgot" && (
            <div className="form-field">
              <label htmlFor="auth-password" className="form-label">
                Contraseña
              </label>
              <input
                id="auth-password"
                type="password"
                className="form-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={8}
                placeholder={mode === "register" ? "Mínimo 8 caracteres" : ""}
                disabled={loading}
              />
              {mode === "register" && <PasswordRequirements password={password} />}
              {mode === "login" && (
                <button
                  type="button"
                  className="auth-forgot-link"
                  onClick={goToForgotPassword}
                  disabled={loading}
                >
                  ¿Olvidaste tu contraseña?
                </button>
              )}
            </div>
          )}

          {error && <p className="message error">{error}</p>}
          {success && <p className="message ok">{success}</p>}

          <button
            type="submit"
            className="primary-button auth-submit"
            disabled={loading || (mode === "register" && !isPasswordValid(password))}
          >
            {loading
              ? "Cargando…"
              : mode === "login"
                ? "Ingresar"
                : mode === "register"
                  ? "Crear cuenta"
                  : "Enviar link de recuperación"}
          </button>
        </form>

        {mode === "forgot" ? (
          <button type="button" className="auth-switch" onClick={backToLogin} disabled={loading}>
            Volver a ingresar
          </button>
        ) : (
          <button type="button" className="auth-switch" onClick={toggleMode} disabled={loading}>
            {mode === "login"
              ? "¿No tienes cuenta? Regístrate"
              : "¿Ya tienes cuenta? Ingresa"}
          </button>
        )}
      </div>
    </div>
  );
}
