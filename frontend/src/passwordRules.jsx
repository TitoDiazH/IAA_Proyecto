import { Check, X } from "lucide-react";

export const PASSWORD_RULES = [
  { label: "Mínimo 8 caracteres", test: (pw) => pw.length >= 8 },
  { label: "Una letra mayúscula", test: (pw) => /[A-Z]/.test(pw) },
  { label: "Una letra minúscula", test: (pw) => /[a-z]/.test(pw) },
  { label: "Un número", test: (pw) => /[0-9]/.test(pw) },
  { label: "Un carácter especial (!@#$%...)", test: (pw) => /[^A-Za-z0-9]/.test(pw) },
];

export function isPasswordValid(pw) {
  return PASSWORD_RULES.every((rule) => rule.test(pw));
}

export function PasswordRequirements({ password }) {
  return (
    <ul className="password-requirements">
      {PASSWORD_RULES.map((rule) => {
        const met = rule.test(password);
        return (
          <li
            key={rule.label}
            className={`password-requirement${met ? " password-requirement--met" : ""}`}
          >
            {met ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}
            {rule.label}
          </li>
        );
      })}
    </ul>
  );
}
