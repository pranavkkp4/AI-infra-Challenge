interface StatePanelProps {
  state: "loading" | "error" | "empty";
  message?: string;
  retry?: () => void;
}

export function StatePanel({ state, message, retry }: StatePanelProps) {
  return (
    <section className={`state-panel ${state}`} role={state === "error" ? "alert" : "status"}>
      <span className="state-glyph">{state === "loading" ? "//" : state === "error" ? "!" : "0"}</span>
      <div>
        <strong>{state === "loading" ? "Retrieving operational records" : state === "error" ? "Data link interrupted" : "No records in this view"}</strong>
        <p>{message ?? "The requested operational dataset is not currently available."}</p>
      </div>
      {retry && <button className="text-button" onClick={retry}>Retry connection</button>}
    </section>
  );
}
