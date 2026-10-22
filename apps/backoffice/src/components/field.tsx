import type { ReactNode } from 'react';

/** Champ libelle, avec aide et message d'erreur relies au controle (lecteurs d'ecran). */
export function Field(props: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: (describedBy: string | undefined) => ReactNode;
}) {
  const hintId = props.hint ? `${props.id}-hint` : undefined;
  const errorId = props.error ? `${props.id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      {props.children(describedBy)}
      {props.hint && (
        <span id={hintId} className="hint">
          {props.hint}
        </span>
      )}
      {props.error && (
        <span id={errorId} className="error">
          {props.error}
        </span>
      )}
    </div>
  );
}
