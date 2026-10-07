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
  // getAuditEvents, // Audit Trail is intentionally hidden for the current demo.
  getConfig,
  getDashboard,
  getHealth,
  getReviewQueue,
  getVendor,
  listMasterVendors,
  listVendors,
  processVendor,
  reviewVendor,
  uploadVendorDocuments,
} from "./api";

const AUTO_EXTRACT_FIELDS = [
  "legal_name",
  "tax_id",
  "pan",
  "bank_account",
  "ifsc",
  "registered_address",
  "contact_name",
  "contact_email",
  "contact_phone",
  "categories",
];

const statusTone = {
  APPROVED: "success",
  VERIFIED: "success",
  VERIFIED_WITH_OVERRIDE: "success",
  PASS: "success",
  ACTION_REQUIRED: "warning",
  REVIEW: "warning",
  REVIEW_REQUIRED: "warning",
  REJECTED: "danger",
  REJECT: "danger",
  FAIL: "danger",
  MISMATCH: "danger",
  NOT_FOUND: "danger",
  ERROR: "danger",
  WAIT_FOR_DOCUMENTS: "warning",
  REQUEST_INFORMATION: "warning",
  APPROVE: "success",
  ACTIVE: "success",
  COMPLETE: "success",
  REGISTERED: "success",
  EXPIRED: "danger",
  PENDING_REVIEW: "warning",
  NOT_AVAILABLE: "neutral",
  SUSPENDED: "warning",
  BLOCKED: "danger",
};

const statusLabel = {
  APPROVED: "Approved",
  ACTION_REQUIRED: "Needs Information",
  REVIEW_REQUIRED: "Needs Review",
  REJECTED: "Rejected",
};

function titleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatStatus(value) {
  return statusLabel[value] || titleCase(value || "Unknown");
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
    <div className={`toast ${toast.tone || "success"}`} role="status" aria-live="polite">
      {toast.tone === "danger" ? <XCircle size={18} /> : <CheckCircle2 size={18} />}
      <span>{toast.message}</span>
      <button onClick={onClose} aria-label="Dismiss Notification"><X size={16} /></button>
    </div>
  );
}

function CheckList({ checks = [] }) {
  if (!checks.length) {
    return (
      <EmptyState
        title="No verification checks"
        copy="Verification Checks appear after the required document set is complete."
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

function AuditLifecycle({ events = [] }) {
  if (!events.length) {
    return <EmptyState title="No History Available" copy="Case lifecycle events will appear here." icon={History} />;
  }

  const sorted = [...events].sort((a, b) => {
    const timeDiff = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
    if (timeDiff !== 0) return timeDiff;
    return Number(a.details?.stage_order || 99) - Number(b.details?.stage_order || 99);
  });

  const detailFor = (event) => {
    const details = event.details || {};
    if (event.event_type === "DOCUMENT_SUBMITTED") {
      return details.message || "Vendor documents were received for processing.";
    }
    if (event.event_type === "AI_EXTRACTION_COMPLETE") {
      const extracted = Number(details.documents_extracted || 0);
      const failed = Number(details.documents_failed || 0);
      return failed
        ? `${extracted} document(s) extracted successfully; ${failed} document(s) need attention.`
        : `${extracted} document(s) were read and structured by AI.`;
    }
    if (event.event_type === "VERIFICATION_COMPLETE") {
      return `${Number(details.check_count || 0)} verification check(s) completed against configured sources.`;
    }
    if (event.event_type === "COMPLETENESS_CHECK_COMPLETE") {
      const missing = details.missing_documents || [];
      return missing.length
        ? `Waiting For: ${missing.join(", ")}`
        : "Document completeness check completed.";
    }
    if (event.event_type === "STATUS_UPDATE") {
      return details.recommendation
        ? `Agent Recommendation: ${formatStatus(details.recommendation)}`
        : "Case status updated.";
    }
    if (event.event_type === "REVIEW_DECISION") {
      return details.comment
        ? `Reviewer Note: ${details.comment}`
        : "Human Review decision recorded.";
    }
    return event.action || "Case activity recorded.";
  };

  const IconFor = ({ type }) => {
    if (type === "DOCUMENT_SUBMITTED") return <UploadCloud size={17} />;
    if (type === "AI_EXTRACTION_COMPLETE") return <FileSearch size={17} />;
    if (type === "VERIFICATION_COMPLETE" || type === "COMPLETENESS_CHECK_COMPLETE") return <SearchCheck size={17} />;
    if (type === "REVIEW_DECISION") return <UserCheck size={17} />;
    if (type === "STATUS_UPDATE") return <ShieldCheck size={17} />;
    return <CheckCircle2 size={17} />;
  };

  return (
    <div className="order-history">
      {sorted.map((event, index) => {
        const current = index === sorted.length - 1;
        return (
          <div className={`order-history-step ${current ? "current" : "complete"}`} key={event.id || `${event.event_type}-${index}`}>
            <div className="order-history-rail">
              <div className="order-history-dot"><IconFor type={event.event_type} /></div>
              {index < sorted.length - 1 && <div className="order-history-line" />}
            </div>
            <div className="order-history-content">
              <div className="order-history-head">
                <strong>{titleCase(event.action || event.event_type)}</strong>
                {event.event_type === "STATUS_UPDATE" && event.details?.status
                  ? <StatusPill value={event.details.status} />
                  : event.event_type === "REVIEW_DECISION" && event.details?.final_status
                    ? <StatusPill value={event.details.final_status} />
                    : null}
              </div>
              <p>{detailFor(event)}</p>
              <span>{event.actor || "System"} · {formatDate(event.created_at)}</span>
            </div>
          </div>
        );
      })}
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
          <span>Auto-Approval Threshold</span>
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

function MissingDocumentUpload({ result, config, onUpdated, title = "Supply Missing Evidence", compact = false }) {
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
      const payload = await uploadVendorDocuments(result.vendor_id, files);
      await onUpdated?.(payload);
      setFiles([]);
    } catch (err) {
      setError(err.message || "Could not upload missing documents.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`panel missing-upload ${compact ? "compact" : ""}`}>
      <div className="panel-title"><UploadCloud size={19} /> {title}</div>
      <div className="missing-upload-body">
        <p>
          {result.missing_documents?.length
            ? <>Required: <strong>{result.missing_documents.join(", ")}</strong></>
            : <>Upload the requested supporting document(s) to continue this application.</>}
        </p>
        <input type="file" multiple onChange={(e) => setFiles(validate(e.target.files))} />
        {files.length > 0 && <div className="compact-file-list">{files.map((file) => <span key={file.name}>{file.name}</span>)}</div>}
        {error && <div className="form-error"><XCircle size={18} />{error}</div>}
        <button className="primary-button" disabled={busy || !files.length} onClick={submit}>
          {busy ? <><RefreshCw className="spin" size={17} /> Re-Running Verification…</> : <><UploadCloud size={17} /> Upload And Continue</>}
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
          <div className="eyebrow">Verification Complete</div>
          <h2>{result.vendor_name}</h2>
          <div className="pill-row">
            <StatusPill value={result.overall_status} />
            <span className="recommendation">Agent Recommendation: <strong>{formatStatus(result.recommendation)}</strong></span>
          </div>
        </div>
        <button className="ghost-button" onClick={onReset}>Start new intake</button>
      </div>

      <div className="metric-grid">
        <Metric label="Documents Read" value={result.extractions?.length || 0} icon={FileCheck2} />
        <Metric label="Checks Verified" value={verified} icon={CheckCircle2} tone="success" />
        <Metric label="Checks Flagged" value={flagged} icon={AlertTriangle} tone={flagged ? "danger" : "neutral"} />
        <Metric label={result.overall_status === "ACTION_REQUIRED" ? "Extraction Confidence" : "Verification Confidence"} value={formatPercent(result.confidence_score)} icon={BarChart3} />
      </div>

      {result.missing_documents?.length > 0 && (
        <div className="callout warning"><AlertTriangle size={20} /><div><strong>Additional Information Required</strong><p>{result.missing_documents.join(", ")}</p></div></div>
      )}

      {result.reasons?.length > 0 && result.overall_status !== "APPROVED" && (
        <div className="panel">
          <div className="panel-title"><AlertTriangle size={19} /> Decision Explanation</div>
          <ul className="reason-list">{result.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        </div>
      )}

      {result.overall_status === "ACTION_REQUIRED" && (
        <MissingDocumentUpload result={result} config={config} onUpdated={onUpdated} />
      )}

      <div className="two-column">
        <div className="panel"><div className="panel-title"><SearchCheck size={19} /> Verification Checks</div><CheckList checks={result.checks} /></div>
        <div className="panel"><div className="panel-title"><Activity size={19} /> Agent Activity</div><Timeline events={result.events} /></div>
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
        <div className="panel-title"><FileText size={19} /> Extracted Document Data</div>
        <div className="documents-grid">{result.extractions?.map((item, index) => <ExtractionCard key={`${item.filename}-${index}`} item={item} />)}</div>
      </div>
    </section>
  );
}

function MasterVendorTable({ rows, onOpenCase }) {
  const openRow = (row) => {
    if (row.source_case_id) onOpenCase(row.source_case_id);
  };

  return (
    <div className="table-wrap">
      <table className="case-table master-vendor-table">
        <thead>
          <tr>
            <th>Vendor</th>
            <th>Categories</th>
            <th>Region</th>
            <th>Verification</th>
            <th>KYC / KYB</th>
            <th>Bank</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.vendor_code}
              className={row.source_case_id ? "clickable-row" : ""}
              tabIndex={row.source_case_id ? 0 : undefined}
              onClick={() => openRow(row)}
              onKeyDown={(event) => {
                if (row.source_case_id && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  openRow(row);
                }
              }}
            >
              <td>
                <strong>{row.legal_name}</strong>
                <div className="table-subtext mono">{row.vendor_code}</div>
                {row.tax_id && <div className="table-subtext">Tax ID: {row.tax_id}</div>}
                {row.primary_contact_email && <div className="table-subtext">{row.primary_contact_email}</div>}
              </td>
              <td>
                <div className="category-list">
                  {(row.categories || []).length
                    ? row.categories.map((category) => <span key={category}>{category}</span>)
                    : <span className="registered-only">Uncategorized</span>}
                </div>
              </td>
              <td>{row.region || "—"}</td>
              <td><StatusPill value={row.verification_status || "NOT_AVAILABLE"} /></td>
              <td><StatusPill value={row.kyc_status || "NOT_AVAILABLE"} /></td>
              <td><StatusPill value={row.bank_verification_status || "NOT_AVAILABLE"} /></td>
              <td><StatusPill value={row.status || "ACTIVE"} /></td>
              <td>
                {row.source_case_id
                  ? <button
                      className="icon-button row-action"
                      aria-label={"Open " + row.legal_name + " onboarding case"}
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenCase(row.source_case_id);
                      }}
                    ><ChevronRight size={18} /></button>
                  : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function DashboardView({ onOpenCase }) {
  const [data, setData] = useState(null);
  const [masterVendors, setMasterVendors] = useState([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [region, setRegion] = useState("");
  const [verificationStatus, setVerificationStatus] = useState("");
  const [kycStatus, setKycStatus] = useState("");
  const [bankStatus, setBankStatus] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    const [dashboardResult, masterResult] = await Promise.allSettled([
      getDashboard(),
      listMasterVendors(),
    ]);

    if (dashboardResult.status === "fulfilled") {
      setData(dashboardResult.value);
    }
    if (masterResult.status === "fulfilled") {
      setMasterVendors(masterResult.value);
    }

    const failures = [dashboardResult, masterResult]
      .filter((item) => item.status === "rejected")
      .map((item) => item.reason?.message || "Unable to load dashboard data.");

    if (failures.length) {
      setError(failures.join(" · "));
    }
    setBusy(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const categories = Array.from(new Set(masterVendors.flatMap((row) => row.categories || []))).sort();
  const regions = Array.from(new Set(masterVendors.map((row) => row.region).filter(Boolean))).sort();
  const verificationStatuses = Array.from(new Set(masterVendors.map((row) => row.verification_status).filter(Boolean))).sort();
  const kycStatuses = Array.from(new Set(masterVendors.map((row) => row.kyc_status).filter(Boolean))).sort();
  const bankStatuses = Array.from(new Set(masterVendors.map((row) => row.bank_verification_status).filter(Boolean))).sort();

  const visibleVendors = masterVendors.filter((row) => {
    const needle = query.trim().toLowerCase();
    const searchMatch = !needle || [
      row.vendor_code,
      row.legal_name,
      row.registration_number,
      row.tax_id,
      row.primary_contact_name,
      row.primary_contact_email,
      row.region,
      ...(row.categories || []),
    ].some((value) => String(value || "").toLowerCase().includes(needle));

    return searchMatch
      && (!status || row.status === status)
      && (!category || (row.categories || []).includes(category))
      && (!region || row.region === region)
      && (!verificationStatus || row.verification_status === verificationStatus)
      && (!kycStatus || row.kyc_status === kycStatus)
      && (!bankStatus || row.bank_verification_status === bankStatus);
  });

  const activeCount = masterVendors.filter((row) => row.status === "ACTIVE").length;

  return (
    <section className="page-stack">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Global Vendor Master</div>
          <h1>Master Dashboard</h1>
          <p>Approved vendors promoted into the shared Supabase Vendor Master for reuse across Finance, Procurement and other teams.</p>
        </div>
        <button className="ghost-button" onClick={load} disabled={busy}>
          <RefreshCw className={busy ? "spin" : ""} size={17} /> Refresh
        </button>
      </div>

      {error && <div className="form-error"><XCircle size={18} />{error}</div>}

      {busy && !data ? (
        <div className="loading-card"><RefreshCw className="spin" /> Loading Global Vendor Master…</div>
      ) : (
        <>
          <div className="metric-grid dashboard-metrics">
            <Metric label="Master Vendors" value={data?.registered_vendor_count ?? masterVendors.length} icon={Building2} />
            <Metric label="Active Vendors" value={activeCount} icon={CheckCircle2} tone="success" />
            <Metric label="Needs Human Review" value={data?.review_required_cases} icon={UserCheck} tone="warning" />
            <Metric label="Needs Information" value={data?.action_required_cases} icon={CircleAlert} tone="warning" />
          </div>

          <div className="dashboard-summary-strip">
            <div><span>Onboarding Cases</span><strong>{data?.total_cases ?? "—"}</strong></div>
            <div><span>Approval Rate</span><strong>{formatPercent(data?.approval_rate)}</strong></div>
            <div><span>Average Confidence</span><strong>{formatPercent(data?.average_confidence_score)}</strong></div>
            <div><span>Auto-Approval Threshold</span><strong>{data?.auto_approval_threshold === null || data?.auto_approval_threshold === undefined ? "Not Configured" : formatPercent(data.auto_approval_threshold)}</strong></div>
            <div><span>Recently Updated</span><strong>{formatDate(data?.recently_updated_at)}</strong></div>
          </div>

          <div className="toolbar panel master-toolbar master-filter-toolbar">
            <div className="search-field">
              <Search size={17} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search Vendor, Vendor ID, Tax ID, Category Or Contact"
              />
            </div>

            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All Statuses</option>
              {["ACTIVE", "SUSPENDED", "BLOCKED", "EXPIRED"].map((value) => (
                <option value={value} key={value}>{titleCase(value)}</option>
              ))}
            </select>

            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All Categories</option>
              {categories.map((value) => <option value={value} key={value}>{value}</option>)}
            </select>

            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="">All Regions</option>
              {regions.map((value) => <option value={value} key={value}>{value}</option>)}
            </select>

            <select value={verificationStatus} onChange={(e) => setVerificationStatus(e.target.value)}>
              <option value="">All Verification</option>
              {verificationStatuses.map((value) => <option value={value} key={value}>{titleCase(value)}</option>)}
            </select>

            <select value={kycStatus} onChange={(e) => setKycStatus(e.target.value)}>
              <option value="">All KYC/KYB</option>
              {kycStatuses.map((value) => <option value={value} key={value}>{titleCase(value)}</option>)}
            </select>

            <select value={bankStatus} onChange={(e) => setBankStatus(e.target.value)}>
              <option value="">All Bank Status</option>
              {bankStatuses.map((value) => <option value={value} key={value}>{titleCase(value)}</option>)}
            </select>

            <span className="master-count">{visibleVendors.length} Of {masterVendors.length} Vendors</span>
          </div>

          <div className="panel">
            <div className="panel-title"><Building2 size={19} /> Global Vendor Master</div>
            {visibleVendors.length
              ? <MasterVendorTable rows={visibleVendors} onOpenCase={onOpenCase} />
              : <EmptyState title="No Master Vendors Found" copy="No approved vendor matches the current filters." icon={Building2} />}
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
        <thead><tr><th>Vendor</th><th>Status</th><th>Confidence</th><th>Category</th><th>Submitted</th><th /></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className="clickable-row"
              tabIndex={0}
              onClick={() => onOpen(row.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onOpen(row.id);
                }
              }}
            >
              <td><strong>{row.legal_name}</strong><div className="table-subtext mono">{row.id}</div><div className="table-subtext">{row.region || "Region Not Set"}</div></td>
              <td><StatusPill value={row.status} /></td>
              <td>{formatPercent(row.confidence_score)}</td>
              <td>{row.category || "—"}</td>
              <td>{formatDate(row.created_at)}</td>
              <td><button className="icon-button row-action" aria-label={`Open ${row.legal_name} case`} onClick={(event) => { event.stopPropagation(); onOpen(row.id); }}><ChevronRight size={18} /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function CasesView({ initialCaseId = null, config }) {
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

  if (selected) return <CaseDetail vendorId={selected} config={config} onBack={() => setSelected(null)} />;

  return (
    <section className="page-stack">
      <div className="section-heading"><div><div className="eyebrow">Case Management</div><h1>Vendor Cases</h1><p>Search, filter and inspect every submitted verification case.</p></div></div>
      <div className="toolbar panel">
        <div className="search-field"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search Vendor Name Or Case ID" /></div>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="REVIEW_REQUIRED">Needs Review</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="ACTION_REQUIRED">Needs Information</option>
        </select>
        <button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button>
      </div>
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      {busy ? <div className="loading-card"><RefreshCw className="spin" /> Loading Cases…</div> : rows.length ? (
        <div className="panel"><CaseTable rows={rows} onOpen={setSelected} /></div>
      ) : <EmptyState title="No matching cases" copy="Change the search or status filter, or submit a new vendor." icon={ClipboardList} />}
    </section>
  );
}

function SourceHint({ meta }) {
  if (!meta) return null;
  const manual = meta.extraction_method === "manual_override" || meta.source === "Manual entry";
  return (
    <div className={`field-source ${manual ? "manual" : "ai"}`}>
      <span>{manual ? "Manual Entry" : "AI Extracted"} · {meta.source}</span>
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
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    categories: "",
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
      setFields((current) => {
        const next = { ...current };
        AUTO_EXTRACT_FIELDS.forEach((field) => {
          if (!manualEdits.has(field)) next[field] = "";
        });
        return next;
      });
      return;
    }

    let active = true;
    setExtracting(true);
    setApiError("");
    extractDocuments(files)
      .then((payload) => {
        if (!active) return;
        const suggestions = payload.field_suggestions || {};
        setExtraction(payload);
        setFieldMeta(suggestions);
        setFields((current) => {
          const next = { ...current };
          AUTO_EXTRACT_FIELDS.forEach((field) => {
            if (manualEdits.has(field)) return;
            next[field] = suggestions[field]?.value ?? "";
          });
          return next;
        });
      })
      .catch((err) => active && setApiError(err.message || "Document extraction failed."))
      .finally(() => active && setExtracting(false));
    return () => { active = false; };
  }, [files]);

  const updateField = (name, value) => {
    setFields((current) => ({ ...current, [name]: value }));
    setManualEdits((current) => new Set([...current, name]));
    if (AUTO_EXTRACT_FIELDS.includes(name)) {
      setFieldMeta((current) => ({
        ...current,
        [name]: {
          value,
          confidence: 1,
          source: "Manual entry",
          extraction_method: "manual_override",
        },
      }));
    }
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

    Object.entries(config?.intake?.validation_patterns || {}).forEach(([field, pattern]) => {
      const value = String(fields[field] || "").trim();
      if (!value || !pattern) return;
      try {
        if (!(new RegExp(pattern)).test(value)) {
          next[field] = "Value does not match the configured format.";
        }
      } catch {
        // Invalid backend regex configuration should not block the user.
      }
    });

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
  const averageExtraction = extraction?.overall_extraction_confidence ?? null;
  const stage = submitting ? 3 : files.length ? 2 : 1;

  const renderInput = (name, label, props = {}) => (
    <div className="form-field">
      <label className="field-label" htmlFor={name}>{label}{requiredFields.includes(name) && <span className="required-mark" aria-label="Required"> *</span>}</label>
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
        <div><div className="eyebrow">Vendor Intake</div><h1>New Vendor Onboarding</h1><p>Upload vendor evidence, review AI-extracted information, and submit the application for verification.</p></div>
        <button className="ghost-button" onClick={reset}><RefreshCw size={16} /> Reset</button>
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
            <strong>Drop Documents Here</strong>
            {policy && <p>{(policy.supported_extensions || []).join(", ")} · {policy.max_file_size_mb} MB per file · {policy.max_files} files maximum</p>}
            <label className="primary-button file-button">
              Choose Files
              <input type="file" multiple onChange={(e) => setFiles(validateFiles(e.target.files))} />
            </label>
          </div>

          {files.length > 0 && (
            <div className="file-list">
              {files.map((file) => (
                <div className="file-row" key={`${file.name}-${file.size}`}>
                  <FileText size={18} />
                  <div className="file-meta"><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></div>
                  <button type="button" className="icon-button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((items) => items.filter((item) => item !== file))}><X size={17} /></button>
                </div>
              ))}
            </div>
          )}

          {extracting && <div className="loading-inline"><RefreshCw className="spin" size={16} /> Extracting documents…</div>}

          {extraction && (
            <>
              <div className="extraction-summary">
                <div><span>Documents Processed</span><strong>{extraction.documents?.length || 0}</strong></div>
                <div><span>Extraction Completeness</span><strong>{formatPercent(averageExtraction)}</strong></div>
                <div><span>Fields Extracted</span><strong>{extraction.extracted_field_count ?? 0}/{extraction.extractable_field_count ?? AUTO_EXTRACT_FIELDS.length}</strong></div>
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
          <div className="panel-title"><Building2 size={19} /> Vendor Information</div>
          <div className="form-grid">
            {renderInput("legal_name", "Legal vendor name")}
            {renderInput("tax_id", "Tax ID / GSTIN")}
            {renderInput("pan", "PAN")}
            {renderInput("bank_account", "Bank account")}
            {renderInput("ifsc", "IFSC / SWIFT")}
            {renderInput("registered_address", "Registered address")}
            {renderInput("contact_name", "Primary contact name")}
            {renderInput("contact_email", "Primary contact email", { type: "email" })}
            {renderInput("contact_phone", "Primary contact phone")}
            {renderInput("categories", "Categories / capabilities", { placeholder: "IT Hardware, Laptops, Networking" })}
            {renderInput("region", "Region", { list: "region-options" })}
            {renderInput("submitted_by", "Submitted by")}
          </div>
          <div className="category-suggestions">
            {(config?.intake?.categories || []).map((value) => (
              <button
                type="button"
                className="category-suggestion"
                key={value}
                onClick={() => {
                  const current = fields.categories
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean);
                  if (!current.some((item) => item.toLowerCase() === value.toLowerCase())) {
                    updateField("categories", [...current, value].join(", "));
                  }
                }}
              >+ {value}</button>
            ))}
          </div>
          <datalist id="region-options">{(config?.intake?.regions || []).map((value) => <option value={value} key={value} />)}</datalist>

          <label className="compliance-row">
            <input type="checkbox" checked={fields.compliance_confirmed} onChange={(e) => updateField("compliance_confirmed", e.target.checked)} />
            <span>I confirm that the submitted vendor information and documents are authorized for verification.</span>
          </label>
          {errors.compliance_confirmed && <div className="field-error">{errors.compliance_confirmed}</div>}

          {apiError && <div className="form-error"><XCircle size={18} />{apiError}</div>}

          <button className="primary-button submit-button" disabled={submitting || extracting || !files.length}>
            {submitting ? <><RefreshCw className="spin" size={18} /> Verifying…</> : <><SearchCheck size={18} /> Verify And Submit</>}
          </button>
        </form>
      </div>
    </section>
  );
}

function DocumentList({ documents = [] }) {
  if (!documents.length) return <EmptyState title="No Documents" copy="No document metadata is associated with this case." icon={FileText} />;
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

function CaseDetail({ vendorId, config, onBack }) {
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
  const tabs = [
    "overview",
    "submission",
    "scorecard",
    // "history", // Audit Trail / case history disabled for the current demo.
  ];

  return (
    <section className="page-stack">
      <button className="back-button" onClick={onBack}><ArrowLeft size={17} /> Back To Cases</button>
      <div className={`result-hero ${statusTone[vendor.status] || "neutral"}`}>
        <div className="result-hero-icon"><Building2 size={30} /></div>
        <div className="result-hero-copy">
          <div className="eyebrow">Vendor Case</div>
          <h2>{vendor.legal_name}</h2>
          <div className="pill-row"><StatusPill value={vendor.status} /><span className="recommendation mono">{vendor.id}</span></div>
        </div>
        <button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button>
      </div>

      <div className="detail-tabs">
        {tabs.map((value) => <button className={tab === value ? "active" : ""} key={value} onClick={() => setTab(value)}>{value === "submission" ? "Original Submission" : value}</button>)}
      </div>

      {tab === "overview" && (
        <div className="page-stack">
          {vendor.status === "ACTION_REQUIRED" && (
            <div className="continue-application priority-action">
              <div className="callout warning">
                <CircleAlert size={20} />
                <div>
                  <strong>Additional Information Required</strong>
                  <p>
                    {latest.missing_documents?.length
                      ? `Missing: ${latest.missing_documents.join(", ")}. Upload the requested document to continue this same case.`
                      : "Upload the requested evidence to continue this same case."}
                  </p>
                </div>
              </div>
              <MissingDocumentUpload
                result={{ vendor_id: vendor.id, missing_documents: latest.missing_documents || [] }}
                config={config}
                title="Upload Missing Documents"
                compact
                onUpdated={async () => {
                  await load();
                  setTab("overview");
                }}
              />
            </div>
          )}

          <div className="metric-grid case-metrics">
            <Metric label={vendor.status === "ACTION_REQUIRED" ? "Extraction Confidence" : "Verification Confidence"} value={formatPercent(latest.confidence_score)} icon={BarChart3} />
            {vendor.risk_level && <Metric label="Risk Level" value={titleCase(vendor.risk_level)} icon={AlertTriangle} tone={vendor.risk_level === "HIGH" ? "danger" : vendor.risk_level === "MEDIUM" ? "warning" : "neutral"} />}
            {(vendor.categories?.length || vendor.category) && (
              <Metric
                label="Categories"
                value={(vendor.categories || [vendor.category]).filter(Boolean).join(", ")}
                icon={ClipboardList}
              />
            )}
            {vendor.region && <Metric label="Region" value={vendor.region} icon={Building2} />}
            {vendor.last_reviewer && <Metric label="Last Reviewer" value={vendor.last_reviewer} icon={UserCheck} />}
            <Metric label="Last Updated" value={formatDate(vendor.updated_at)} icon={History} />
          </div>
          {vendor.reasons?.length > 0 && <div className="panel decision-panel"><div className="panel-title"><AlertTriangle size={18} /> Decision Explanation</div><ul className="reason-list">{vendor.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}

          <div className="two-column">
            <div className="panel"><div className="panel-title"><SearchCheck size={19} /> Validation Checks</div><CheckList checks={latest.checks || []} /></div>
            <div className="panel"><div className="panel-title"><Activity size={19} /> Latest Agent Run</div><Timeline events={latest.events || []} /></div>
          </div>
          <div className="panel"><div className="panel-title"><FileText size={19} /> Documents</div><DocumentList documents={detail.documents} /></div>
        </div>
      )}

      {tab === "submission" && (
        <div className="two-column">
          <div className="panel">
            <div className="panel-title"><Building2 size={19} /> Submitted Form Values</div>
            <dl className="submission-grid">
              {Object.keys(submitted).length ? Object.entries(submitted).map(([key, value]) => (
                <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value || "—")}</dd></div>
              )) : <EmptyState title="No Submitted Form Metadata" copy="This case predates structured intake metadata." icon={ClipboardList} />}
            </dl>
          </div>
          <div className="panel"><div className="panel-title"><FileText size={19} /> Attached Documents</div><DocumentList documents={detail.documents} /></div>
        </div>
      )}

      {tab === "scorecard" && (
        <div className="panel"><div className="panel-title"><BarChart3 size={19} /> Verification Scorecard</div><Scorecard items={latest.scorecard || []} overall={latest.confidence_score} threshold={config?.verification?.auto_approval_threshold ?? null} /></div>
      )}

      {/*
      {tab === "history" && (
        <div className="panel">
          <div className="panel-title"><History size={19} /> Complete Case History</div>
          <AuditLifecycle events={detail.audit_events || []} />
        </div>
      )}
      Audit Trail / case history disabled for the current demo.
      */}
    </section>
  );
}

function ReviewCase({ vendorId, config, onCompleted, notify }) {
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
      setError("Reviewer Notes are required for rejection and information requests.");
      return;
    }
    setReviewBusy(true);
    setError("");
    try {
      await reviewVendor(vendorId, { decision, reviewer: reviewer.trim(), comment: comment.trim() });
      notify({ message: "Human Review decision saved.", tone: "success" });
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
      <div className="result-hero warning review-hero">
        <div className="result-hero-icon"><UserCheck size={28} /></div>
        <div className="result-hero-copy"><div className="eyebrow">Human Review</div><h2>{vendor.legal_name}</h2><div className="pill-row"><StatusPill value={vendor.status} /><span className="recommendation">Agent Recommendation: <strong>{formatStatus(vendor.agent_recommendation)}</strong></span><span className="recommendation">Confidence: <strong>{formatPercent(latest.confidence_score)}</strong></span>{vendor.risk_level && <span className="recommendation">Risk: <strong>{titleCase(vendor.risk_level)}</strong></span>}</div></div>
      </div>
      {vendor.reasons?.length > 0 && <div className="panel"><div className="panel-title"><AlertTriangle size={19} /> Why This Case Needs Review</div><ul className="reason-list">{vendor.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}
      <div className="two-column">
        <div className="panel"><div className="panel-title"><SearchCheck size={19} /> Validation Results</div><CheckList checks={latest.checks || []} /></div>
        <div className="panel"><div className="panel-title"><BarChart3 size={19} /> Scorecard</div><Scorecard items={latest.scorecard || []} overall={latest.confidence_score} threshold={config?.verification?.auto_approval_threshold ?? null} /></div>
      </div>
      <div className="panel"><div className="panel-title"><FileText size={19} /> Documents</div><DocumentList documents={detail.documents} /></div>
      <div className="panel review-form">
        <div className="panel-title"><UserCheck size={19} /> Human Decision</div>
        <div className="review-grid">
          <div><label className="field-label">Reviewer</label><input className="text-input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} /></div>
          <div><label className="field-label">Reviewer Notes</label><textarea className="text-area" value={comment} onChange={(e) => setComment(e.target.value)} /></div>
        </div>
        {error && <div className="form-error"><XCircle size={18} />{error}</div>}
        <div className="review-actions">
          <button className="ghost-button" disabled={reviewBusy} onClick={() => decide("REQUEST_INFORMATION")}><CircleAlert size={17} /> Request Information</button>
          <button className="danger-button" disabled={reviewBusy} onClick={() => decide("REJECT")}><XCircle size={17} /> Reject</button>
          <button className="primary-button" disabled={reviewBusy} onClick={() => decide("APPROVE")}><CheckCircle2 size={17} /> Approve</button>
        </div>
      </div>
    </div>
  );
}

function ReviewQueueView({ config, notify }) {
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
      <div className="section-heading"><div><div className="eyebrow">Exception handling</div><h1>Human Review Queue</h1><p>Review only the cases routed by the verification agent.</p></div><button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button></div>
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      <div className="review-layout">
        <aside className="panel review-sidebar">
          <div className="search-field"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search Review Cases" /></div>
          {busy ? <div className="loading-inline"><RefreshCw className="spin" size={16} /> Loading…</div> : filtered.length ? (
            <div className="review-case-list">
              {filtered.map((row) => (
                <button className={selected === row.id ? "active" : ""} key={row.id} onClick={() => setSelected(row.id)}>
                  <div className="review-case-copy">
                    <div className="review-case-title"><strong>{row.legal_name}</strong><StatusPill value={row.status} /></div>
                    <span>{row.reasons?.[0] || "Manual Review Required."}</span>
                    <small>{row.risk_level ? `${titleCase(row.risk_level)} Risk · ` : ""}{formatPercent(row.confidence_score)} Confidence</small>
                  </div>
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
          ) : <EmptyState title="Review Queue Is Clear" copy="No cases currently require human review." icon={ShieldCheck} />}
        </aside>
        <div>{selected ? <ReviewCase vendorId={selected} config={config} onCompleted={load} notify={notify} /> : <EmptyState title="No Review Case Selected" copy="Select a case from the review queue." icon={UserCheck} />}</div>
      </div>
    </section>
  );
}

/* AUDIT_TRAIL_DISABLED
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
      const payload = await getAuditEvents();
      setEvents(payload);
      const firstVendorId = payload?.[0]?.vendor_id;
      if (firstVendorId) setExpanded((current) => current.size ? current : new Set([firstVendorId]));
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
      <div className="section-heading">
        <div>
          <div className="eyebrow">Traceability</div>
          <h1>Audit Trail</h1>
          <p>Follow each vendor case like an order journey, from document submission to the current status.</p>
        </div>
        <button className="ghost-button" onClick={load}><RefreshCw size={16} /> Refresh</button>
      </div>
      <div className="toolbar panel">
        <div className="search-field"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search Case, Vendor, Actor Or Event" /></div>
        <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          <option value="">All Event Types</option>
          {eventTypes.map((type) => <option value={type} key={type}>{titleCase(type)}</option>)}
        </select>
      </div>
      {error && <div className="form-error"><XCircle size={18} />{error}</div>}
      {busy ? <div className="loading-card"><RefreshCw className="spin" /> Loading Audit History…</div> : Object.keys(groups).length ? (
        <div className="audit-groups">
          {Object.entries(groups).map(([vendorId, group]) => {
            const open = expanded.has(vendorId);
            const vendorMeta = group.find((event) => event.verification_vendors)?.verification_vendors || {};
            const vendorName = vendorMeta.legal_name || vendorId;
            const currentStatus = vendorMeta.status || group.find((event) => event.details?.status)?.details?.status;
            const lastUpdated = vendorMeta.updated_at || [...group].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0]?.created_at;
            return (
              <div className="panel audit-group" key={vendorId}>
                <button className="audit-group-head" onClick={() => toggle(vendorId)}>
                  <div className="audit-case-identity">
                    <strong>{vendorName}</strong>
                    <span className="mono">{vendorId}</span>
                    <small>Last Updated: {formatDate(lastUpdated)}</small>
                  </div>
                  <div className="audit-case-status">
                    {currentStatus && <StatusPill value={currentStatus} />}
                    <span>{open ? "Hide History" : "View History"} {open ? <ChevronDown size={17} /> : <ChevronRight size={17} />}</span>
                  </div>
                </button>
                {open && <AuditLifecycle events={group} />}
              </div>
            );
          })}
        </div>
      ) : <EmptyState title="No Audit Events" copy="No events match the current filters." icon={History} />}
    </section>
  );
}
*/

export default function App() {
  const [view, setView] = useState("intake");
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
    ["intake", "New Vendor Onboarding", UploadCloud],
    ["dashboard", "Master Dashboard", LayoutDashboard],
    ["cases", "Cases", ClipboardList],
    ["review", "Review Queue", UserCheck],
    // ["audit", "Audit Trail", History], // Disabled for the current demo.
  ];

  return (
    <div className="app-shell">
      <Toast toast={toast} onClose={() => setToast(null)} />
      <header className="topbar">
        <button className="brand" aria-label="Open New Vendor Onboarding" onClick={() => { setCaseId(null); setView("intake"); }}>
          <div className="brand-mark"><ShieldCheck size={22} /></div>
          <div><strong>Vendor Verify</strong><span>Verification Agent</span></div>
        </button>
        <nav className="nav-tabs">
          {nav.map(([key, label, Icon]) => (
            <button className={view === key ? "active" : ""} key={key} onClick={() => { setCaseId(null); setView(key); }}><Icon size={16} /> {label}</button>
          ))}
        </nav>
        <div className={`health-badge ${health}`}>
          <span className="health-dot" />
          <div><strong>{health === "online" ? "Backend Connected" : health === "offline" ? "Backend Unavailable" : "Checking Backend"}</strong><span>{API_BASE_URL}</span></div>
        </div>
      </header>

      <main className="main-content">
        {configError && <div className="form-error"><XCircle size={18} />{configError}</div>}
        {view === "dashboard" && <DashboardView onOpenCase={openCase} />}
        {view === "cases" && <CasesView key={caseId || "cases"} initialCaseId={caseId} config={config} />}
        {view === "intake" && (config ? <NewVendorView config={config} notify={setToast} /> : <div className="loading-card"><RefreshCw className="spin" /> Loading intake policy…</div>)}
        {view === "review" && <ReviewQueueView config={config} notify={setToast} />}
        {/* {view === "audit" && <AuditView />} Audit Trail disabled for the current demo. */}
      </main>

      <footer className="footer">
        <span>Vendor Verification Workspace</span>
        <span>Document Intake · Verification · Human Review</span>
      </footer>
    </div>
  );
}
