import type { FormEvent, RefObject } from "react";

export function AskPex({
  question,
  answer,
  asking,
  inputRef,
  compact = false,
  questions = [],
  onQuestion,
  onSubmit,
  onAskPrompt,
}: {
  question: string;
  answer: string;
  asking: boolean;
  inputRef?: RefObject<HTMLInputElement | null>;
  compact?: boolean;
  questions?: string[];
  onQuestion: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onAskPrompt?: (prompt: string) => void;
}) {
  const inputId = compact ? "pex-ask-deck" : "pex-ask-inspector";
  return (
    <form className={`ask-pex ${compact ? "ask-pex-compact" : ""}`} onSubmit={onSubmit}>
      <label htmlFor={inputId}>Ask PEX</label>
      <p>
        Answers from canonical local state. Inspects attached workspaces when that
        state is not enough. Does not interrupt a worker.
      </p>
      {questions.length ? (
        <div className="ask-chips" aria-label="Questions from attached workers">
          {questions.map((prompt) => (
            <button
              type="button"
              className="ghost ask-chip"
              disabled={asking}
              onClick={() => (onAskPrompt ? onAskPrompt(prompt) : onQuestion(prompt))}
              key={prompt}
            >
              {prompt}
            </button>
          ))}
        </div>
      ) : null}
      <div className="ask-row">
        <input
          ref={inputRef}
          id={inputId}
          value={question}
          onChange={(event) => onQuestion(event.target.value)}
          placeholder="What needs me right now?"
        />
        <button className="solid" type="submit" disabled={asking || !question.trim()}>
          {asking ? "Checking…" : "Ask"}
        </button>
      </div>
      {answer ? <output aria-live="polite">{answer}</output> : null}
    </form>
  );
}
