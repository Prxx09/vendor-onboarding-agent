import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  ClipboardList,
  FileCheck2,
  FileSearch,
  FileText,
  History,
  LayoutDashboard,
  ListFilter,
  RefreshCw,
  Search,
  SearchCheck,
  ShieldCheck,
  UploadCloud,
  UserCheck,
  X,
  XCircle,
} from "lucide-react";
import {
  API_BASE_URL,
  extractDocuments,
  getAuditEvents,
  getConfig,
  getDashboard,
  getHealth,
  getReviewQueue,
  getVendor,
  listVendors,
  processVendor,
  reviewVendor,
  uploadVendorDocuments,
} from "./api";

const statusTone = {
  APPROVED: "success",
  VERIFIED: "success",
  PASS: "success",
  ACTION_REQUIRED: "warning",
  REVIEW: "warning",
  REVIEW_REQUIRED: "danger",
  REJECTED: "danger",
  REJECT: "danger",
  FAIL: "danger",
  MISMATCH: "danger",
  NOT_FOUND: "danger",
  ERROR: "danger",
  WAIT_FOR_DOCUMENTS: "warning",
  REQUEST_INFORMATION: "warning",
  APPROVE: "success",
};

const statusLabel = {
  APPROVED: "Approved",
  ACTION_REQUIRED: "Needs information",
  REVIEW_REQUIRED: "Needs review",
  REJECTED: "Rejected",
};

function formatStatus(value) {
  return statusLabel[value] || String(value || "Unknown").replaceAll("_", " ");
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(1)}%`;
}

function StatusPill({ value }) {
  return (
    <span className={`status-pill ${statusTone[value] || "neutral"}`}>
      {formatStatus(value)}
    </span>
  );
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

function Metric({ label, value, icon: Icon, tone = "neutral", helper }) {
  return (
    <div className={`metric-card ${tone}`}>
      <div className="metric-icon"><Icon size={20} /></div>
      <div>
        <div className="metric-value">{value ?? "—"}</div>
        <div className="metric-label">{label}</div>
        {helper && <div className="metric-helper">{helper}</div>}
      </div>
    </div>
  );
}

function Toast({ toast, onClose }) {
  if (!toast) return null;
  return (
    <div className={`toast ${toast.tone || "success"}`}>
      {toast.tone === "danger" ? <XCircle size={18} /> : <CheckCircle2 size={18} />}
      <span>{toast.message}</span>
      <button onClick={onClose}><X size={16} /></button>
    </div>
  );
}

function CheckList({ checks = [] }) {
  if (!checks.length) {
    return (
      <EmptyState
        title="No verification checks"
        copy="Verification checks appear after the required document set is complete."
        icon={SearchCheck}
      />
    );
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
              <strong>{String(check.source || "verification").replaceAll("_", " ").replaceAll(":", " / ")}</strong>
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
    return <EmptyState title="No activity" copy="Agent events will be shown here." icon={Activity} />;
  }
  return (
    <div className="timeline">
      {events.map((event, index) => (
        <div className="timeline-item" key={`${event.step}-${index}`}>
          <div className="timeline-dot" />
          <div>
            <div className="timeline-step">{String(event.step || "").replaceAll("_", " ")}</div>
            <p>{event.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function Scorecard({ items = [], threshold = null, overall = null }) {
  if (!items.length) {
    return <EmptyState title="No scorecard available" copy="A scorecard is generated after verification." icon={BarChart3} />;
  }
  return (
    <div className="scorecard-stack">
      <div className="score-summary">
        <div>
          <span>Overall confidence</span>
          <strong>{formatPercent(overall)}</strong>
        </div>
        <div>
          <span>Auto-approval threshold</span>
          <strong>{threshold === null || threshold === undefined ? "Not configured" : formatPercent(threshold)}</strong>
        </div>
        <div>
          <span>Sections reviewed</span>
          <strong>{items.length}</strong>
        </div>
      </div>
      <div className="score-grid">
        {items.map((item, index) => (
          <article className="score-card" key={`${item.name}-${index}`}>
            <div className="score-card-head">
              <strong>{item.name}</strong>
              <StatusPill value={item.status} />
            </div>
            <div className="score-number">{formatPercent(item.score)}</div>
            <div className="progress-track"><div style={{ width: `${Math.max(0, Math.min(100, Number(item.score) || 0))}%` }} /></div>
            <p>{item.message}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

function ExtractionCard({ item }) {
  const fields = [
    ["Legal name", item.legal_name],
    ["Registration no.", item.registration_number],
    ["Tax ID", item.tax_id],
    ["PAN", item.pan],
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
          <div className="eyebrow">{String(item.document_type || "document").replaceAll("_", " ")}</div>
          <h4>{item.filename}</h4>
        </div>
        <span className="confidence">{formatPercent((Number(item.confidence) || 0) * 100)}</span>
      </div>
      <dl className="field-grid">
        {fields.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>
        ))}
      </dl>
      {item.notes?.length > 0 && <div className="note-box">{item.notes.join(" · ")}</div>}
    </article>
  );
}

function MissingDocumentUpload({ result, config, onUpdated }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const policy = config?.upload;

  const validate = (incoming) => {
    if (!policy) return [];
    const accepted = [];
    const allowed = policy.supported_extensions || [];
    for (const file of Array.from(incoming || [])) {
      const lower = file.name.toLowerCase();
      if (!allowed.some((ext) => lower.endsWith(ext))) {
        setError(`${file.name} is not an accepted document type.`);
        continue;
      }
      if (file.size > Number(policy.max_file_size_mb) * 1024 * 1024) {
        setError(`${file.name} exceeds the configured file-size limit.`);
        continue;
      }
      accepted.push(file);
    }
    return accepted;
  };

  const submit = async () => {
    if (!files.length) return;
    setBusy(true);
    setError("");
    try {
      onUpdated(await uploadVendorDocuments(result.vendor_id, files));
    } catch (err) {
      setError(err.message || "Could not upload missing documents.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel missing-upload">
      <div className="panel-title"><UploadCloud size={19} /> Supply missing evidence</div>
      <div className="missing-upload-body">
        <p>Required: <strong>{result.missing_documents.join(", ")}</strong></p>
        <input type="file" multiple onChange={(e) => setFiles(validate(e.target.files))} />
        {files.length > 0 && <div className="compact-file-list">{files.map((file) => <span key={file.name}>{file.name}</span>)}</div>}
        {error && <div className="form-error"><XCircle size={18} />{error}</div>}
        <button className="primary-button" disabled={busy || !files.length} onClick={submit}>
          {busy ? <><RefreshCw className="spin" size={17} /> Re-running verification…</> : <><UploadCloud size={17} /> Upload and resume</>}
        </button>
      </div>
    </div>
  );
}

function VerificationResult({ result, config, onReset, onUpdated }) {
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
            <span className="recommendation">Agent recommendation: <strong>{formatStatus(result.recommendation)}</strong></span>
          </div>
        </div>
        <button className="ghost-button" onClick={onReset}>Start new intake</button>
      </div>

      <div className="metric-grid">
        <Metric label="Documents read" value={result.extractions?.length || 0} icon={FileCheck2} />
        <Metric label="Checks verified" value={verified} icon={CheckCircle2} tone="success" />
        <Metric label="Checks flagged" value={flagged} icon={AlertTriangle} tone={flagged ? "danger" : "neutral"} />
        <Metric label="Confidence" value={formatPercent(result.confidence_score)} icon={BarChart3} />
      </div>

      {result.missing_documents?.length > 0 && (
        <div className="callout warning"><AlertTriangle size={20} /><div><strong>Additional information required</strong><p>{result.missing_documents.join(", ")}</p></div></div>
      )}

      {result.reasons?.length > 0 && result.overall_status !== "APPROVED" && (
        <div className="panel">
          <div className="panel-title"><AlertTriangle size={19} /> Decision explanation</div>
          <ul className="reason-list">{result.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        </div>
      )}

      {result.overall_status === "ACTION_REQUIRED" && (
        <MissingDocumentUpload result={result} config={config} onUpdated={onUpdated} />
      )}

      <div className="two-column">
        <div className="panel"><div className="panel-title"><SearchCheck size={19} /> Verification checks</div><CheckList checks={result.checks} /></div>
        <div className="panel"><div className="panel-title"><Activity size={19} /> Agent activity</div><Timeline events={result.events} /></div>
      </div>

      <div className="panel">
        <div className="panel-title"><BarChart3 size={19} /> Scorecard</div>
        <Scorecard
          items={result.scorecard || []}
          overall={result.confidence_score}
          threshold={config?.verification?.auto_approval_threshold ?? null}
        />
      </div>

      <div className="panel">
        <div className="panel-title"><FileText size={19} /> Extracted document data</div>
        <div className="documents-grid">{result.extractions?.map((item, index) => <ExtractionCard key={`${item.filename}-${index}`} item={item} />)}</div>
      </div>
    </section>
  );
}

function DashboardView({ onOpenCase }) {
  const [data, setData] = useState(null);
  const [recent, setRecent] = useState([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const [dashboard, cases] = await Promise.all([getDashboard(), listVendors()]);
      setData(dashboard);
      setRecent(cases.slice(0, 8));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="page-stack">
      <div className="section-heading">
        <div><div className="eyebrow">Operations</div><h1>Vendor onboarding dashboard</h1><p>Live metrics from the verification backend and Supabase case records.</p></div>
        <button className="ghost-button" onClick={load} disabled={busy}><RefreshCw className={busy ? "spin" : ""} size={17} /> Refresh</button>
      </div>
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      {busy && !data ? <div className="loading-card"><RefreshCw className="spin" /> Loading dashboard…</div> : (
        <>
          <div className="metric-grid dashboard-metrics">
            <Metric label="Total vendor cases" value={data?.total_cases} icon={ClipboardList} />
            <Metric label="Approved vendors" value={data?.approved_cases} icon={CheckCircle2} tone="success" />
            <Metric label="Needs human review" value={data?.review_required_cases} icon={UserCheck} tone="danger" />
            <Metric label="Average confidence" value={formatPercent(data?.average_confidence_score)} icon={BarChart3} />
            <Metric label="Approval rate" value={formatPercent(data?.approval_rate)} icon={ShieldCheck} tone="success" />
            <Metric
              label="Auto-approval threshold"
              value={data?.auto_approval_threshold === null || data?.auto_approval_threshold === undefined ? "Not configured" : formatPercent(data.auto_approval_threshold)}
              icon={SearchCheck}
            />
          </div>
          <div className="dashboard-meta">Recently updated: <strong>{formatDate(data?.recently_updated_at)}</strong></div>
          <div className="panel">
            <div className="panel-title"><History size={19} /> Recently updated cases</div>
            {recent.length ? <CaseTable rows={recent} onOpen={onOpenCase} /> : <EmptyState title="No cases yet" copy="Submitted vendor cases will appear here." icon={ClipboardList} />}
          </div>
        </>
      )}
    </section>
  );
}

function CaseTable({ rows, onOpen }) {
  return (
    <div className="table-wrap">
      <table className="case-table">
        <thead><tr><th>Vendor</th><th>Case ID</th><th>Category</th><th>Region</th><th>Submitted</th><th>Confidence</th><th>Status</th><th /></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td><strong>{row.legal_name}</strong></td>
              <td className="mono">{row.id}</td>
              <td>{row.category || "—"}</td>
              <td>{row.region || "—"}</td>
              <td>{formatDate(row.created_at)}</td>
              <td>{formatPercent(row.confidence_score)}</td>
              <td><StatusPill value={row.status} /></td>
              <td><button className="icon-button" onClick={() => onOpen(row.id)}><ChevronRight size={17} /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CasesView({ initialCaseId = null }) {
  const [selected, setSelected] = useState(initialCaseId);
  const [rows, setRows] = useState([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setRows(await listVendors({ status, query }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [status, query]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  if (selected) return <CaseDetail vendorId={selected} onBack={() => setSelected(null)} />;

  return (
    <section className="page-stack">
      <div className="section-heading"><div><div className="eyebrow">Case management</div><h1>Vendor cases</h1><p>Search, filter and inspect every submitted verification case.</p></div></div>
      <div className="toolbar panel">
        <div className="search-field"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search vendor name or case ID" /></div>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="REVIEW_REQUIRED">Needs review</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="ACTION_REQUIRED">Needs information</option>
        </select>
        <button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button>
      </div>
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      {busy ? <div className="loading-card"><RefreshCw className="spin" /> Loading cases…</div> : rows.length ? (
        <div className="panel"><CaseTable rows={rows} onOpen={setSelected} /></div>
      ) : <EmptyState title="No matching cases" copy="Change the search or status filter, or submit a new vendor." icon={ClipboardList} />}
    </section>
  );
}

function SourceHint({ meta }) {
  if (!meta) return null;
  return (
    <div className="field-source">
      <span>Source: {meta.source}</span>
      <span>Confidence: {formatPercent(Number(meta.confidence) * 100)}</span>
    </div>
  );
}

function ProgressSteps({ stage }) {
  const steps = ["Upload", "Verify", "Submit"];
  return (
    <div className="intake-steps">
      {steps.map((label, index) => {
        const number = index + 1;
        return (
          <div className={`intake-step ${stage >= number ? "active" : ""} ${stage > number ? "done" : ""}`} key={label}>
            <span>{stage > number ? <CheckCircle2 size={16} /> : number}</span>
            <strong>{label}</strong>
          </div>
        );
      })}
    </div>
  );
}

function NewVendorView({ config, notify }) {
  const emptyFields = {
    legal_name: "",
    tax_id: "",
    pan: "",
    bank_account: "",
    ifsc: "",
    registered_address: "",
    contact_email: "",
    category: "",
    region: "",
    submitted_by: "",
    compliance_confirmed: false,
  };
  const [fields, setFields] = useState(emptyFields);
  const [files, setFiles] = useState([]);
  const [fieldMeta, setFieldMeta] = useState({});
  const [extraction, setExtraction] = useState(null);
  const [manualEdits, setManualEdits] = useState(new Set());
  const [extracting, setExtracting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState("");
  const [result, setResult] = useState(null);

  const policy = config?.upload;
  const requiredFields = config?.verification?.required_intake_fields || [];
  const requiredDocs = config?.verification?.required_documents || {};

  const validateFiles = useCallback((incoming) => {
    if (!policy) return [];
    setApiError("");
    const current = Array.from(files);
    const unique = new Map(current.map((file) => [`${file.name}-${file.size}`, file]));
    let combined = current.reduce((sum, file) => sum + file.size, 0);

    for (const file of Array.from(incoming || [])) {
      const extensionOk = (policy.supported_extensions || []).some((ext) => file.name.toLowerCase().endsWith(ext));
      if (!extensionOk) {
        setApiError(`${file.name} is not an accepted document type.`);
        continue;
      }
      if (file.size > Number(policy.max_file_size_mb) * 1024 * 1024) {
        setApiError(`${file.name} exceeds the configured per-file upload limit.`);
        continue;
      }
      if (unique.size >= Number(policy.max_files)) {
        setApiError("The configured maximum number of documents has been reached.");
        break;
      }
      if (combined + file.size > Number(policy.max_combined_size_mb) * 1024 * 1024) {
        setApiError("The selected documents exceed the configured combined upload limit.");
        break;
      }
      const key = `${file.name}-${file.size}`;
      if (!unique.has(key)) {
        unique.set(key, file);
        combined += file.size;
      }
    }
    return Array.from(unique.values());
  }, [files, policy]);

  useEffect(() => {
    if (!files.length) {
      setExtraction(null);
      setFieldMeta({});
      return;
    }

    let active = true;
    setExtracting(true);
    setApiError("");
    extractDocuments(files)
      .then((payload) => {
        if (!active) return;
        setExtraction(payload);
        setFieldMeta(payload.field_suggestions || {});
        setFields((current) => {
          const next = { ...current };
          Object.entries(payload.field_suggestions || {}).forEach(([field, meta]) => {
            if (!manualEdits.has(field) && !next[field]) next[field] = meta.value ?? "";
          });
          return next;
        });
      })
      .catch((err) => active && setApiError(err.message || "Document extraction failed."))
      .finally(() => active && setExtracting(false));
    return () => { active = false; };
  }, [files, manualEdits]);

  const updateField = (name, value) => {
    setFields((current) => ({ ...current, [name]: value }));
    setManualEdits((current) => new Set([...current, name]));
    setErrors((current) => ({ ...current, [name]: "" }));
  };

  const validate = () => {
    const next = {};
    requiredFields.forEach((field) => {
      if (field === "compliance_confirmed") {
        if (!fields.compliance_confirmed) next[field] = "Compliance confirmation is required.";
      } else if (!String(fields[field] ?? "").trim()) {
        next[field] = "This field is required.";
      }
    });
    if (fields.contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.contact_email)) {
      next.contact_email = "Enter a valid email address.";
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!validate()) return;
    if (!files.length) {
      setApiError("Upload at least one vendor document.");
      return;
    }
    setSubmitting(true);
    setApiError("");
    try {
      const payload = await processVendor({ fields, files });
      setResult(payload);
      notify({ message: "Vendor verification completed.", tone: "success" });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setApiError(err.message || "Vendor submission failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setFields(emptyFields);
    setFiles([]);
    setFieldMeta({});
    setExtraction(null);
    setManualEdits(new Set());
    setErrors({});
    setApiError("");
    setResult(null);
  };

  if (result) {
    return <VerificationResult result={result} config={config} onReset={reset} onUpdated={setResult} />;
  }

  const extractedTypes = new Set((extraction?.documents || []).map((doc) => doc.document_type));
  const coverage = Object.entries(requiredDocs).map(([type, label]) => ({
    type,
    label,
    present: extractedTypes.has(type),
  }));
  const averageExtraction = extraction?.documents?.length
    ? extraction.documents.reduce((sum, doc) => sum + Number(doc.confidence || 0), 0) / extraction.documents.length * 100
    : null;
  const stage = submitting ? 3 : files.length ? 2 : 1;

  const renderInput = (name, label, props = {}) => (
    <div className="form-field">
      <label className="field-label" htmlFor={name}>{label}{requiredFields.includes(name) && <span className="required-mark"> required</span>}</label>
      <input
        id={name}
        className={`text-input ${errors[name] ? "invalid" : ""}`}
        value={fields[name]}
        onChange={(e) => updateField(name, e.target.value)}
        {...props}
      />
      <SourceHint meta={fieldMeta[name]} />
      {errors[name] && <div className="field-error">{errors[name]}</div>}
    </div>
  );

  return (
    <section className="page-stack">
      <div className="section-heading">
        <div><div className="eyebrow">New vendor intake</div><h1>Capture, extract and verify vendor evidence.</h1><p>Documents are OCR'd first, then structured by Groq and verified against configured backend sources.</p></div>
        <button className="ghost-button" onClick={reset}><RefreshCw size={16} /> Reset intake</button>
      </div>

      <ProgressSteps stage={stage} />

      <div className="intake-layout">
        <div className="panel upload-panel">
          <div className="panel-title"><UploadCloud size={19} /> Documents</div>
          <div
            className={`drop-zone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              setFiles(validateFiles(e.dataTransfer.files));
            }}
          >
            <UploadCloud size={30} />
            <strong>Drop vendor documents here</strong>
            {policy && <p>{(policy.supported_extensions || []).join(", ")} · {policy.max_file_size_mb} MB per file · {policy.max_files} files maximum</p>}
            <label className="primary-button file-button">
              Choose files
              <input type="file" multiple onChange={(e) => setFiles(validateFiles(e.target.files))} />
            </label>
          </div>

          {files.length > 0 && (
            <div className="file-list">
              {files.map((file) => (
                <div className="file-row" key={`${file.name}-${file.size}`}>
                  <FileText size={18} />
                  <div className="file-meta"><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></div>
                  <button type="button" className="icon-button" onClick={() => setFiles((items) => items.filter((item) => item !== file))}><X size={17} /></button>
                </div>
              ))}
            </div>
          )}

          {extracting && <div className="loading-inline"><RefreshCw className="spin" size={16} /> Extracting documents…</div>}

          {extraction && (
            <>
              <div className="extraction-summary">
                <div><span>Documents processed</span><strong>{extraction.documents?.length || 0}</strong></div>
                <div><span>Extraction confidence</span><strong>{formatPercent(averageExtraction)}</strong></div>
                <div><span>Required fields missing</span><strong>{extraction.missing_required_fields?.length || 0}</strong></div>
              </div>
              <div className="coverage-list">
                {coverage.map((item) => (
                  <span className={item.present ? "covered" : "missing"} key={item.type}>
                    {item.present ? <CheckCircle2 size={14} /> : <CircleAlert size={14} />}{item.label}
                  </span>
                ))}
              </div>
              {extraction.errors?.length > 0 && (
                <div className="form-error"><XCircle size={18} />{extraction.errors.map((item) => `${item.filename}: ${item.message}`).join(" · ")}</div>
              )}
            </>
          )}
        </div>

        <form className="panel intake-form" onSubmit={submit}>
          <div className="panel-title"><Building2 size={19} /> Vendor information</div>
          <div className="form-grid">
            {renderInput("legal_name", "Legal vendor name")}
            {renderInput("tax_id", "Tax ID / GSTIN")}
            {renderInput("pan", "PAN")}
            {renderInput("bank_account", "Bank account")}
            {renderInput("ifsc", "IFSC / SWIFT")}
            {renderInput("registered_address", "Registered address")}
            {renderInput("contact_email", "Contact email", { type: "email" })}
            {renderInput("category", "Vendor category", { list: "category-options" })}
            {renderInput("region", "Region", { list: "region-options" })}
            {renderInput("submitted_by", "Submitted by")}
          </div>
          <datalist id="category-options">{(config?.intake?.categories || []).map((value) => <option value={value} key={value} />)}</datalist>
          <datalist id="region-options">{(config?.intake?.regions || []).map((value) => <option value={value} key={value} />)}</datalist>

          <label className="compliance-row">
            <input type="checkbox" checked={fields.compliance_confirmed} onChange={(e) => updateField("compliance_confirmed", e.target.checked)} />
            <span>I confirm that the submitted vendor information and documents are authorized for verification.</span>
          </label>
          {errors.compliance_confirmed && <div className="field-error">{errors.compliance_confirmed}</div>}

          {apiError && <div className="form-error"><XCircle size={18} />{apiError}</div>}

          <button className="primary-button submit-button" disabled={submitting || extracting || !files.length}>
            {submitting ? <><RefreshCw className="spin" size={18} /> Verifying and submitting…</> : <><SearchCheck size={18} /> Verify and submit vendor</>}
          </button>
        </form>
      </div>
    </section>
  );
}

function DocumentList({ documents = [] }) {
  if (!documents.length) return <EmptyState title="No documents" copy="No document metadata is associated with this case." icon={FileText} />;
  return (
    <div className="document-list">
      {documents.map((doc) => (
        <div className="document-row" key={doc.id}>
          <FileText size={18} />
          <div><strong>{doc.filename}</strong><span>{String(doc.document_type || "document").replaceAll("_", " ")} · {formatDate(doc.created_at)}</span></div>
          {doc.available && doc.document_url ? (
            <a className="ghost-button" href={doc.document_url} target="_blank" rel="noreferrer">Open</a>
          ) : <span className="unavailable">File unavailable</span>}
        </div>
      ))}
    </div>
  );
}

function CaseDetail({ vendorId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [tab, setTab] = useState("overview");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

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

  if (busy) return <div className="loading-card"><RefreshCw className="spin" /> Loading case…</div>;
  if (error || !detail) return <div className="form-error"><XCircle size={18} />{error || "Case not found."}<button className="ghost-button" onClick={onBack}>Back</button></div>;

  const vendor = detail.vendor || {};
  const latest = detail.agent_runs?.[0] || {};
  const submitted = vendor.submitted_data || {};
  const tabs = ["overview", "submission", "scorecard", "history"];

  return (
    <section className="page-stack">
      <button className="back-button" onClick={onBack}><ArrowLeft size={17} /> Back to cases</button>
      <div className={`result-hero ${statusTone[vendor.status] || "neutral"}`}>
        <div className="result-hero-icon"><Building2 size={30} /></div>
        <div className="result-hero-copy">
          <div className="eyebrow">Vendor case</div>
          <h2>{vendor.legal_name}</h2>
          <div className="pill-row"><StatusPill value={vendor.status} /><span className="recommendation mono">{vendor.id}</span></div>
        </div>
        <button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button>
      </div>

      <div className="detail-tabs">
        {tabs.map((value) => <button className={tab === value ? "active" : ""} key={value} onClick={() => setTab(value)}>{value === "submission" ? "Original submission" : value}</button>)}
      </div>

      {tab === "overview" && (
        <div className="page-stack">
          <div className="metric-grid">
            <Metric label="Confidence" value={formatPercent(latest.confidence_score)} icon={BarChart3} />
            <Metric label="Category" value={vendor.category || "—"} icon={ClipboardList} />
            <Metric label="Region" value={vendor.region || "—"} icon={Building2} />
            <Metric label="Last updated" value={formatDate(vendor.updated_at)} icon={History} />
          </div>
          {vendor.reasons?.length > 0 && <div className="panel"><div className="panel-title"><AlertTriangle size={19} /> Decision explanation</div><ul className="reason-list">{vendor.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}
          <div className="two-column">
            <div className="panel"><div className="panel-title"><SearchCheck size={19} /> Validation checks</div><CheckList checks={latest.checks || []} /></div>
            <div className="panel"><div className="panel-title"><Activity size={19} /> Latest agent run</div><Timeline events={latest.events || []} /></div>
          </div>
          <div className="panel"><div className="panel-title"><FileText size={19} /> Documents</div><DocumentList documents={detail.documents} /></div>
        </div>
      )}

      {tab === "submission" && (
        <div className="two-column">
          <div className="panel">
            <div className="panel-title"><Building2 size={19} /> Submitted form values</div>
            <dl className="submission-grid">
              {Object.keys(submitted).length ? Object.entries(submitted).map(([key, value]) => (
                <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value || "—")}</dd></div>
              )) : <EmptyState title="No submitted form metadata" copy="This case predates structured intake metadata." icon={ClipboardList} />}
            </dl>
          </div>
          <div className="panel"><div className="panel-title"><FileText size={19} /> Attached documents</div><DocumentList documents={detail.documents} /></div>
        </div>
      )}

      {tab === "scorecard" && (
        <div className="panel"><div className="panel-title"><BarChart3 size={19} /> Verification scorecard</div><Scorecard items={latest.scorecard || []} overall={latest.confidence_score} /></div>
      )}

      {tab === "history" && (
        <div className="panel">
          <div className="panel-title"><History size={19} /> Complete case history</div>
          {detail.audit_events?.length ? (
            <div className="audit-list">
              {detail.audit_events.map((event) => (
                <div className="audit-row" key={event.id}><div><strong>{event.action}</strong><span>{event.actor || "System"} · {formatDate(event.created_at)}</span></div><StatusPill value={event.event_type} /></div>
              ))}
            </div>
          ) : <EmptyState title="No audit events available" copy="Audit events will appear after the case-management migration is applied." icon={History} />}
        </div>
      )}
    </section>
  );
}

function ReviewCase({ vendorId, onCompleted, notify }) {
  const [detail, setDetail] = useState(null);
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(true);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [error, setError] = useState("");

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

  const decide = async (decision) => {
    if (!reviewer.trim()) {
      setError("Reviewer name is required.");
      return;
    }
    if ((decision === "REJECT" || decision === "REQUEST_INFORMATION") && !comment.trim()) {
      setError("Reviewer notes are required for rejection and information requests.");
      return;
    }
    setReviewBusy(true);
    setError("");
    try {
      await reviewVendor(vendorId, { decision, reviewer: reviewer.trim(), comment: comment.trim() });
      notify({ message: "Human review decision saved.", tone: "success" });
      await onCompleted();
    } catch (err) {
      setError(err.message);
    } finally {
      setReviewBusy(false);
    }
  };

  if (busy) return <div className="loading-card"><RefreshCw className="spin" /> Loading review case…</div>;
  if (!detail) return <EmptyState title="No case selected" copy={error || "Select a review case."} icon={UserCheck} />;

  const vendor = detail.vendor || {};
  const latest = detail.agent_runs?.[0] || {};
  return (
    <div className="page-stack">
      <div className="result-hero danger">
        <div className="result-hero-icon"><UserCheck size={28} /></div>
        <div className="result-hero-copy"><div className="eyebrow">Human review</div><h2>{vendor.legal_name}</h2><div className="pill-row"><StatusPill value={vendor.status} /><span className="recommendation">Agent recommendation: <strong>{formatStatus(vendor.agent_recommendation)}</strong></span></div></div>
      </div>
      {vendor.reasons?.length > 0 && <div className="panel"><div className="panel-title"><AlertTriangle size={19} /> Why this case needs review</div><ul className="reason-list">{vendor.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}
      <div className="two-column">
        <div className="panel"><div className="panel-title"><SearchCheck size={19} /> Validation results</div><CheckList checks={latest.checks || []} /></div>
        <div className="panel"><div className="panel-title"><BarChart3 size={19} /> Scorecard</div><Scorecard items={latest.scorecard || []} overall={latest.confidence_score} /></div>
      </div>
      <div className="panel"><div className="panel-title"><FileText size={19} /> Documents</div><DocumentList documents={detail.documents} /></div>
      <div className="panel review-form">
        <div className="panel-title"><UserCheck size={19} /> Human decision</div>
        <div className="review-grid">
          <div><label className="field-label">Reviewer</label><input className="text-input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} /></div>
          <div><label className="field-label">Reviewer notes</label><textarea className="text-area" value={comment} onChange={(e) => setComment(e.target.value)} /></div>
        </div>
        {error && <div className="form-error"><XCircle size={18} />{error}</div>}
        <div className="review-actions">
          <button className="ghost-button" disabled={reviewBusy} onClick={() => decide("REQUEST_INFORMATION")}><CircleAlert size={17} /> Request information</button>
          <button className="danger-button" disabled={reviewBusy} onClick={() => decide("REJECT")}><XCircle size={17} /> Reject</button>
          <button className="primary-button" disabled={reviewBusy} onClick={() => decide("APPROVE")}><CheckCircle2 size={17} /> Approve</button>
        </div>
      </div>
    </div>
  );
}

function ReviewQueueView({ notify }) {
  const [queue, setQueue] = useState([]);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const rows = await getReviewQueue();
      setQueue(rows);
      setSelected((current) => rows.some((row) => row.id === current) ? current : (rows[0]?.id || null));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = queue.filter((row) => {
    const needle = query.trim().toLowerCase();
    return !needle || String(row.legal_name || "").toLowerCase().includes(needle) || String(row.id || "").toLowerCase().includes(needle);
  });

  return (
    <section className="page-stack">
      <div className="section-heading"><div><div className="eyebrow">Exception handling</div><h1>Human review queue</h1><p>Review only the cases routed by the verification agent.</p></div><button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button></div>
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      <div className="review-layout">
        <aside className="panel review-sidebar">
          <div className="search-field"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search review cases" /></div>
          {busy ? <div className="loading-inline"><RefreshCw className="spin" size={16} /> Loading…</div> : filtered.length ? (
            <div className="review-case-list">
              {filtered.map((row) => (
                <button className={selected === row.id ? "active" : ""} key={row.id} onClick={() => setSelected(row.id)}>
                  <div><strong>{row.legal_name}</strong><span>{row.reasons?.[0] || "Manual review required."}</span></div><ChevronRight size={16} />
                </button>
              ))}
            </div>
          ) : <EmptyState title="Review queue is clear" copy="No cases currently require human review." icon={ShieldCheck} />}
        </aside>
        <div>{selected ? <ReviewCase vendorId={selected} onCompleted={load} notify={notify} /> : <EmptyState title="No review case selected" copy="Select a case from the review queue." icon={UserCheck} />}</div>
      </div>
    </section>
  );
}

function AuditView() {
  const [events, setEvents] = useState([]);
  const [query, setQuery] = useState("");
  const [eventType, setEventType] = useState("");
  const [expanded, setExpanded] = useState(new Set());
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setEvents(await getAuditEvents());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const eventTypes = Array.from(new Set(events.map((event) => event.event_type).filter(Boolean))).sort();
  const filtered = events.filter((event) => {
    const needle = query.trim().toLowerCase();
    const vendorName = event.verification_vendors?.legal_name || "";
    const searchMatch = !needle || [event.vendor_id, vendorName, event.actor, event.action].some((value) => String(value || "").toLowerCase().includes(needle));
    const typeMatch = !eventType || event.event_type === eventType;
    return searchMatch && typeMatch;
  });
  const groups = filtered.reduce((acc, event) => {
    const key = event.vendor_id;
    if (!acc[key]) acc[key] = [];
    acc[key].push(event);
    return acc;
  }, {});

  const toggle = (id) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <section className="page-stack">
      <div className="section-heading"><div><div className="eyebrow">Traceability</div><h1>Audit trail</h1><p>Search timestamped vendor-case events from intake through human decision.</p></div><button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button></div>
      <div className="toolbar panel">
        <div className="search-field"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search case, vendor, actor or event" /></div>
        <select value={eventType} onChange={(e) => setEventType(e.target.value)}><option value="">All event types</option>{eventTypes.map((type) => <option value={type} key={type}>{type.replaceAll("_", " ")}</option>)}</select>
      </div>
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      {busy ? <div className="loading-card"><RefreshCw className="spin" /> Loading audit events…</div> : Object.keys(groups).length ? (
        <div className="audit-groups">
          {Object.entries(groups).map(([vendorId, group]) => {
            const open = expanded.has(vendorId);
            const vendorName = group[0]?.verification_vendors?.legal_name || vendorId;
            return (
              <div className="panel audit-group" key={vendorId}>
                <button className="audit-group-head" onClick={() => toggle(vendorId)}>
                  <div><strong>{vendorName}</strong><span className="mono">{vendorId}</span></div><span>{group.length} event(s) {open ? <ChevronDown size={17} /> : <ChevronRight size={17} />}</span>
                </button>
                {open && <div className="audit-list">{group.map((event) => (
                  <div className="audit-row" key={event.id}><div><strong>{event.action}</strong><span>{event.actor || "System"} · {formatDate(event.created_at)}</span></div><StatusPill value={event.event_type} /></div>
                ))}</div>}
              </div>
            );
          })}
        </div>
      ) : <EmptyState title="No audit events" copy="No events match the current filters." icon={History} />}
    </section>
  );
}

export default function App() {
  const [view, setView] = useState("dashboard");
  const [caseId, setCaseId] = useState(null);
  const [health, setHealth] = useState("checking");
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  const [toast, setToast] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([getHealth(), getConfig()]).then(([healthResult, configResult]) => {
      if (!active) return;
      setHealth(healthResult.status === "fulfilled" ? "online" : "offline");
      if (configResult.status === "fulfilled") setConfig(configResult.value);
      else setConfigError(configResult.reason?.message || "Could not load backend configuration.");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(null), 4500);
    return () => clearTimeout(timer);
  }, [toast]);

  const openCase = (id) => {
    setCaseId(id);
    setView("cases");
  };

  const nav = [
    ["dashboard", "Dashboard", LayoutDashboard],
    ["cases", "Cases", ClipboardList],
    ["intake", "New vendor", UploadCloud],
    ["review", "Review queue", UserCheck],
    ["audit", "Audit trail", History],
  ];

  return (
    <div className="app-shell">
      <Toast toast={toast} onClose={() => setToast(null)} />
      <header className="topbar">
        <button className="brand" onClick={() => setView("dashboard")}>
          <div className="brand-mark"><ShieldCheck size={22} /></div>
          <div><strong>Vendor Verify</strong><span>Verification agent</span></div>
        </button>
        <nav className="nav-tabs">
          {nav.map(([key, label, Icon]) => (
            <button className={view === key ? "active" : ""} key={key} onClick={() => { setCaseId(null); setView(key); }}><Icon size={16} /> {label}</button>
          ))}
        </nav>
        <div className={`health-badge ${health}`}>
          <span className="health-dot" />
          <div><strong>{health === "online" ? "Backend connected" : health === "offline" ? "Backend unavailable" : "Checking backend"}</strong><span>{API_BASE_URL}</span></div>
        </div>
      </header>

      <main className="main-content">
        {configError && <div className="form-error"><XCircle size={18} />{configError}</div>}
        {view === "dashboard" && <DashboardView onOpenCase={openCase} />}
        {view === "cases" && <CasesView key={caseId || "cases"} initialCaseId={caseId} />}
        {view === "intake" && (config ? <NewVendorView config={config} notify={setToast} /> : <div className="loading-card"><RefreshCw className="spin" /> Loading intake policy…</div>)}
        {view === "review" && <ReviewQueueView notify={setToast} />}
        {view === "audit" && <AuditView />}
      </main>

      <footer className="footer">
        <span>Verification data and workflow status are loaded from the backend.</span>
        <span>OCR → Groq → verification providers → deterministic routing → human review</span>
      </footer>
    </div>
  );
}
