import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FileCheck2,
  FileText,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  UploadCloud,
  UserCheck,
  X,
  XCircle,
} from "lucide-react";
import {
  API_BASE_URL,
  getHealth,
  getReviewQueue,
  getVendor,
  processVendor,
  reviewVendor,
  uploadVendorDocuments,
} from "./api";

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp"];

const statusTone = {
  APPROVED: "success",
  VERIFIED: "success",
  ACTION_REQUIRED: "warning",
  REVIEW_REQUIRED: "danger",
  REJECTED: "danger",
  REJECT: "danger",
  MISMATCH: "danger",
  NOT_FOUND: "danger",
  ERROR: "danger",
  WAIT_FOR_DOCUMENTS: "warning",
  APPROVE: "success",
};

function StatusPill({ value }) {
  const tone = statusTone[value] || "neutral";
  return <span className={`status-pill ${tone}`}>{String(value || "UNKNOWN").replaceAll("_", " ")}</span>;
}

function EmptyState({ title, copy, icon: Icon = FileText }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={24} /></div>
      <h3>{title}</h3>
      <p>{copy}</p>
    </div>
  );
}

function Metric({ label, value, icon: Icon, tone = "neutral" }) {
  return (
    <div className={`metric-card ${tone}`}>
      <div className="metric-icon"><Icon size={20} /></div>
      <div>
        <div className="metric-value">{value}</div>
        <div className="metric-label">{label}</div>
      </div>
    </div>
  );
}

function CheckList({ checks = [] }) {
  if (!checks.length) {
    return <EmptyState title="No verification checks yet" copy="Checks appear after a complete document set is processed." icon={SearchCheck} />;
  }

  return (
    <div className="check-list">
      {checks.map((check, index) => (
        <div className="check-row" key={`${check.source}-${index}`}>
          <div className={`check-marker ${statusTone[check.status] || "neutral"}`}>
            {check.status === "VERIFIED" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          </div>
          <div className="check-body">
            <div className="check-head">
              <strong>{check.source?.replaceAll("_", " ") || "Verification check"}</strong>
              <StatusPill value={check.status} />
            </div>
            <p>{check.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function Timeline({ events = [] }) {
  if (!events.length) {
    return <EmptyState title="No activity yet" copy="Agent steps will be shown here as verification runs." icon={Activity} />;
  }
  return (
    <div className="timeline">
      {events.map((event, index) => (
        <div className="timeline-item" key={`${event.step}-${index}`}>
          <div className="timeline-dot" />
          <div>
            <div className="timeline-step">{event.step?.replaceAll("_", " ")}</div>
            <p>{event.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function ExtractionCard({ item }) {
  const fields = [
    ["Legal name", item.legal_name],
    ["Registration no.", item.registration_number],
    ["Tax ID", item.tax_id],
    ["Account holder", item.account_holder_name],
    ["Bank", item.bank_name],
    ["Account no.", item.bank_account_number],
    ["IFSC / SWIFT", item.ifsc_swift],
    ["Address", item.registered_address],
    ["Issue date", item.issue_date],
    ["Expiry date", item.expiry_date],
  ].filter(([, value]) => value);

  return (
    <article className="document-card">
      <div className="document-card-head">
        <div>
          <div className="eyebrow">{item.document_type?.replaceAll("_", " ")}</div>
          <h4>{item.filename}</h4>
        </div>
        <span className="confidence">{Math.round((item.confidence || 0) * 100)}%</span>
      </div>
      <dl className="field-grid">
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {item.notes?.length > 0 && (
        <div className="note-box">{item.notes.join(" · ")}</div>
      )}
    </article>
  );
}


function MissingDocumentUpload({ result, onUpdated }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const chooseFiles = (incoming) => {
    setError("");
    const valid = [];
    for (const file of Array.from(incoming || [])) {
      const lower = file.name.toLowerCase();
      if (!SUPPORTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
        setError(`${file.name} is not a supported PDF/image file.`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        setError(`${file.name} exceeds the 20 MB file limit.`);
        continue;
      }
      valid.push(file);
    }
    setFiles(valid);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!files.length) {
      setError("Choose at least one missing document.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const updated = await uploadVendorDocuments(result.vendor_id, files);
      onUpdated(updated);
    } catch (err) {
      setError(err.message || "Could not upload the missing document.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel upload-panel" onSubmit={submit}>
      <div className="panel-title"><UploadCloud size={19} /> Continue this onboarding case</div>
      <p>
        Upload only the missing document(s): {result.missing_documents.join(", ")}.
        Existing stored documents will be reused and the same vendor ID will continue.
      </p>
      <label className="primary-button file-button">
        Choose missing document
        <input
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          onChange={(event) => chooseFiles(event.target.files)}
        />
      </label>
      {files.length > 0 && (
        <div className="file-list">
          {files.map((file) => (
            <div className="file-row" key={`${file.name}-${file.size}`}>
              <FileText size={18} />
              <div className="file-meta">
                <strong>{file.name}</strong>
                <span>{(file.size / 1024 / 1024).toFixed(2)} MB</span>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setFiles((items) => items.filter((item) => item !== file))}
                aria-label={`Remove ${file.name}`}
              >
                <X size={17} />
              </button>
            </div>
          ))}
        </div>
      )}
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      <button className="primary-button submit-button" disabled={busy || !files.length}>
        {busy
          ? <><RefreshCw className="spin" size={18} /> Re-running verification…</>
          : <><SearchCheck size={18} /> Upload and continue verification</>}
      </button>
    </form>
  );
}

function ResultPanel({ result, onReset, onUpdated }) {
  if (!result) return null;
  const verified = result.checks?.filter((item) => item.status === "VERIFIED").length || 0;
  const flagged = (result.checks?.length || 0) - verified;

  return (
    <section className="result-stack">
      <div className={`result-hero ${statusTone[result.overall_status] || "neutral"}`}>
        <div className="result-hero-icon">
          {result.overall_status === "APPROVED" ? <ShieldCheck size={30} /> : <CircleAlert size={30} />}
        </div>
        <div className="result-hero-copy">
          <div className="eyebrow">Verification complete</div>
          <h2>{result.vendor_name}</h2>
          <div className="pill-row">
            <StatusPill value={result.overall_status} />
            <span className="recommendation">Agent recommendation: <strong>{result.recommendation?.replaceAll("_", " ")}</strong></span>
          </div>
        </div>
        <button className="ghost-button" onClick={onReset}>Verify another vendor</button>
      </div>

      <div className="metric-grid">
        <Metric label="Documents read" value={result.extractions?.length || 0} icon={FileCheck2} />
        <Metric label="Checks verified" value={verified} icon={CheckCircle2} tone="success" />
        <Metric label="Checks flagged" value={flagged} icon={AlertTriangle} tone={flagged ? "danger" : "neutral"} />
        <Metric label="Missing documents" value={result.missing_documents?.length || 0} icon={FileText} tone={result.missing_documents?.length ? "warning" : "neutral"} />
      </div>

      {result.missing_documents?.length > 0 && (
        <div className="callout warning">
          <AlertTriangle size={20} />
          <div>
            <strong>Action required</strong>
            <p>Missing: {result.missing_documents.join(", ")}</p>
          </div>
        </div>
      )}

      {result.overall_status === "ACTION_REQUIRED" && (
        <MissingDocumentUpload result={result} onUpdated={onUpdated} />
      )}

      {result.reasons?.length > 0 && result.overall_status !== "APPROVED" && (
        <div className="panel">
          <div className="panel-title"><AlertTriangle size={19} /> Why this vendor was flagged</div>
          <ul className="reason-list">{result.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
        </div>
      )}

      <div className="two-column">
        <div className="panel">
          <div className="panel-title"><SearchCheck size={19} /> Verification checks</div>
          <CheckList checks={result.checks} />
        </div>
        <div className="panel">
          <div className="panel-title"><Activity size={19} /> Agent activity</div>
          <Timeline events={result.events} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-title"><FileText size={19} /> Extracted document data</div>
        <div className="documents-grid">
          {result.extractions?.map((item, index) => <ExtractionCard key={`${item.filename}-${index}`} item={item} />)}
        </div>
      </div>
    </section>
  );
}

function VerifyView() {
  const [legalName, setLegalName] = useState("");
  const [files, setFiles] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem("vendor-verification:last-result") || "null");
    } catch {
      return null;
    }
  });

  const addFiles = useCallback((incoming) => {
    setError("");
    const next = [];
    for (const file of Array.from(incoming || [])) {
      const lower = file.name.toLowerCase();
      if (!SUPPORTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
        setError(`${file.name} is not a supported PDF/image file.`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        setError(`${file.name} exceeds the 20 MB file limit.`);
        continue;
      }
      next.push(file);
    }
    setFiles((current) => {
      const byKey = new Map(current.map((file) => [`${file.name}-${file.size}`, file]));
      next.forEach((file) => byKey.set(`${file.name}-${file.size}`, file));
      return Array.from(byKey.values());
    });
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    if (!files.length) {
      setError("Upload at least one document.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = await processVendor({ legalName, files });
      setResult(payload);
      sessionStorage.setItem("vendor-verification:last-result", JSON.stringify(payload));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err.message || "Verification failed.");
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return <ResultPanel
      result={result}
      onUpdated={(updated) => {
        setResult(updated);
        sessionStorage.setItem("vendor-verification:last-result", JSON.stringify(updated));
        setFiles([]);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }}
      onReset={() => {
        setResult(null);
        sessionStorage.removeItem("vendor-verification:last-result");
        setFiles([]);
        setLegalName("");
      }}
    />;
  }

  return (
    <section className="verify-layout">
      <div className="page-copy">
        <div className="eyebrow">New verification</div>
        <h1>Verify a supplier with evidence, not guesswork.</h1>
        <p>
          Upload the registration, tax and bank documents. The agent extracts text locally,
          structures it with Groq, verifies it against the Supabase demo registries and
          routes exceptions to a human reviewer.
        </p>
        <div className="process-strip">
          <span>OCR</span><ChevronRight size={16} /><span>Groq</span><ChevronRight size={16} />
          <span>Registry checks</span><ChevronRight size={16} /><span>Decision</span>
        </div>
      </div>

      <form className="panel upload-panel" onSubmit={submit}>
        <label className="field-label" htmlFor="legalName">Vendor legal name <span>optional</span></label>
        <input
          id="legalName"
          className="text-input"
          value={legalName}
          onChange={(event) => setLegalName(event.target.value)}
          placeholder="Evergreen Facility Solutions Private Limited"
        />

        <div
          className={`drop-zone ${dragging ? "dragging" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            addFiles(event.dataTransfer.files);
          }}
        >
          <UploadCloud size={30} />
          <strong>Drop vendor documents here</strong>
          <p>PDF, PNG, JPG or WEBP · up to 20 MB each</p>
          <label className="primary-button file-button">
            Choose files
            <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(e) => addFiles(e.target.files)} />
          </label>
        </div>

        <div className="required-docs">
          <span><CheckCircle2 size={15} /> Business registration</span>
          <span><CheckCircle2 size={15} /> Tax certificate</span>
          <span><CheckCircle2 size={15} /> Bank proof</span>
        </div>

        {files.length > 0 && (
          <div className="file-list">
            {files.map((file) => (
              <div className="file-row" key={`${file.name}-${file.size}`}>
                <FileText size={18} />
                <div className="file-meta">
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
                <button type="button" className="icon-button" onClick={() => setFiles((items) => items.filter((item) => item !== file))}>
                  <X size={17} />
                </button>
              </div>
            ))}
          </div>
        )}

        {error && <div className="form-error"><XCircle size={18} />{error}</div>}

        <button className="primary-button submit-button" disabled={busy || !files.length}>
          {busy ? <><RefreshCw className="spin" size={18} /> Running verification…</> : <><SearchCheck size={18} /> Run verification</>}
        </button>
      </form>
    </section>
  );
}

function ReviewDetail({ vendorId, onBack, onReviewed }) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(true);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setDetail(await getVendor(vendorId));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [vendorId]);

  useEffect(() => { load(); }, [load]);

  const submitReview = async (decision) => {
    if (!reviewer.trim()) {
      setError("Enter the reviewer name before making a decision.");
      return;
    }
    setReviewBusy(true);
    setError("");
    try {
      await reviewVendor(vendorId, { decision, reviewer: reviewer.trim(), comment: comment.trim() });
      await onReviewed();
    } catch (err) {
      setError(err.message);
    } finally {
      setReviewBusy(false);
    }
  };

  if (busy) return <div className="loading-card"><RefreshCw className="spin" /> Loading vendor evidence…</div>;
  if (error && !detail) return <div className="form-error"><XCircle size={18} />{error}<button className="ghost-button" onClick={onBack}>Back</button></div>;

  const vendor = detail?.vendor || {};
  const latestRun = detail?.agent_runs?.[0] || {};
  const checks = Array.isArray(latestRun.checks) ? latestRun.checks : [];
  const events = Array.isArray(latestRun.events) ? latestRun.events : [];

  return (
    <section className="result-stack">
      <button className="back-button" onClick={onBack}><ArrowLeft size={17} /> Back to review queue</button>

      <div className="result-hero danger">
        <div className="result-hero-icon"><UserCheck size={30} /></div>
        <div className="result-hero-copy">
          <div className="eyebrow">Human review</div>
          <h2>{vendor.legal_name}</h2>
          <div className="pill-row">
            <StatusPill value={vendor.status} />
            <span className="recommendation">Agent recommendation: <strong>{vendor.agent_recommendation}</strong></span>
          </div>
        </div>
      </div>

      {vendor.reasons?.length > 0 && (
        <div className="panel">
          <div className="panel-title"><AlertTriangle size={19} /> Agent findings</div>
          <ul className="reason-list">{vendor.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
        </div>
      )}

      <div className="two-column">
        <div className="panel">
          <div className="panel-title"><SearchCheck size={19} /> Verification checks</div>
          <CheckList checks={checks} />
        </div>
        <div className="panel">
          <div className="panel-title"><Activity size={19} /> Agent activity</div>
          <Timeline events={events} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-title"><FileText size={19} /> Document evidence</div>
        <div className="documents-grid">
          {detail?.documents?.map((doc) => (
            <ExtractionCard key={doc.id} item={{ filename: doc.filename, document_type: doc.document_type, confidence: Number(doc.confidence || 0), ...(doc.extracted_data || {}) }} />
          ))}
        </div>
      </div>

      <div className="panel review-form">
        <div className="panel-title"><UserCheck size={19} /> Human decision</div>
        <div className="review-grid">
          <div>
            <label className="field-label">Reviewer</label>
            <input className="text-input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Reviewer name" />
          </div>
          <div>
            <label className="field-label">Review note</label>
            <textarea className="text-area" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Record why you are approving or rejecting this exception." />
          </div>
        </div>
        {error && <div className="form-error"><XCircle size={18} />{error}</div>}
        <div className="review-actions">
          <button className="danger-button" disabled={reviewBusy} onClick={() => submitReview("REJECT")}><XCircle size={18} /> Reject vendor</button>
          <button className="primary-button" disabled={reviewBusy} onClick={() => submitReview("APPROVE")}><CheckCircle2 size={18} /> Approve override</button>
        </div>
      </div>
    </section>
  );
}

function ReviewQueueView() {
  const [queue, setQueue] = useState([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setQueue(await getReviewQueue());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (selected) {
    return <ReviewDetail vendorId={selected} onBack={() => setSelected(null)} onReviewed={async () => {
      setSelected(null);
      await load();
    }} />;
  }

  return (
    <section className="queue-page">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Exception handling</div>
          <h1>Human review queue</h1>
          <p>Only vendors flagged by the verification agent appear here.</p>
        </div>
        <button className="ghost-button" onClick={load} disabled={busy}><RefreshCw className={busy ? "spin" : ""} size={17} /> Refresh</button>
      </div>

      {error && <div className="form-error"><XCircle size={18} />{error}</div>}

      {busy ? (
        <div className="loading-card"><RefreshCw className="spin" /> Loading review queue…</div>
      ) : queue.length === 0 ? (
        <EmptyState title="Review queue is clear" copy="Suspicious vendors will appear here automatically." icon={ShieldCheck} />
      ) : (
        <div className="queue-list">
          {queue.map((vendor) => (
            <button className="queue-card" key={vendor.id} onClick={() => setSelected(vendor.id)}>
              <div className="queue-avatar"><Building2 size={21} /></div>
              <div className="queue-copy">
                <div className="queue-topline">
                  <strong>{vendor.legal_name}</strong>
                  <StatusPill value={vendor.status} />
                </div>
                <p>{vendor.reasons?.[0] || "Agent flagged this vendor for manual review."}</p>
                <span>Agent recommendation: {vendor.agent_recommendation || "REJECT"}</span>
              </div>
              <ChevronRight size={20} />
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [view, setView] = useState("verify");
  const [health, setHealth] = useState("checking");

  useEffect(() => {
    let active = true;
    getHealth()
      .then(() => active && setHealth("online"))
      .catch(() => active && setHealth("offline"));
    return () => { active = false; };
  }, []);

  const healthLabel = useMemo(() => ({
    checking: "Checking backend",
    online: "Backend connected",
    offline: "Backend unavailable",
  })[health], [health]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => setView("verify")}>
          <div className="brand-mark"><ShieldCheck size={22} /></div>
          <div><strong>Vendor Verify</strong><span>Agent prototype</span></div>
        </button>

        <nav className="nav-tabs">
          <button className={view === "verify" ? "active" : ""} onClick={() => setView("verify")}><SearchCheck size={17} /> Verify vendor</button>
          <button className={view === "review" ? "active" : ""} onClick={() => setView("review")}><UserCheck size={17} /> Review queue</button>
        </nav>

        <div className={`health-badge ${health}`}>
          <span className="health-dot" />
          <div><strong>{healthLabel}</strong><span>{API_BASE_URL}</span></div>
        </div>
      </header>

      <main className="main-content">
        {view === "verify" ? <VerifyView /> : <ReviewQueueView />}
      </main>

      <footer className="footer">
        <span>Prototype verification data is synthetic.</span>
        <span>OCR → Groq → deterministic verification → human review</span>
      </footer>
    </div>
  );
}
