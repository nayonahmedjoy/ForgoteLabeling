import { useEffect, useState } from "react";

export default function CreateProjectModal({ onClose, onCreate }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Close on Escape.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onCreate(name.trim() || "Untitled Project");
      onClose();
    } catch (err) {
      setError(err.message || "Failed to create project.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <form
        className="modal"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h2>New Project</h2>
        <div>
          <label className="muted">Project name</label>
          <input
            type="text"
            autoFocus
            placeholder="e.g. Street signs dataset"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ marginTop: 6 }}
          />
        </div>
        {error ? <div className="state error" style={{ padding: 0 }}>{error}</div> : null}
        <div className="row between">
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
