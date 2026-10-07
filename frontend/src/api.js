const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim();

const API_BASE_URL = (
  configuredApiBase
  || (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin)
).replace(/\/$/, "");

async function parseResponse(response) {
  if (response.status === 204) return null;

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");

  if (response.ok) {
    if (!isJson) {
      const preview = (await response.text()).slice(0, 120).replace(/\s+/g, " ");
      throw new Error(
        `Expected JSON from ${response.url}, but received ${contentType || "non-JSON content"}`
        + (preview ? `: ${preview}` : ""),
      );
    }
    return response.json();
  }

  let message = `Request failed with status ${response.status}`;
  if (isJson) {
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") message = payload.detail;
      else if (payload?.detail) message = JSON.stringify(payload.detail);
    } catch {
      // Keep the generic HTTP error.
    }
  } else {
    const preview = (await response.text()).slice(0, 120).replace(/\s+/g, " ");
    if (preview) message = `${message}: ${preview}`;
  }
  throw new Error(message);
}

function withQuery(path, params = {}) {
  const url = new URL(`${API_BASE_URL}${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      url.searchParams.set(key, value);
    }
  });
  return url.toString();
}

export async function getHealth() {
  return parseResponse(await fetch(`${API_BASE_URL}/health`));
}

export async function getConfig() {
  return parseResponse(await fetch(`${API_BASE_URL}/api/v1/config`));
}

export async function getDashboard() {
  return parseResponse(await fetch(`${API_BASE_URL}/api/v1/dashboard`));
}

export async function listMasterVendors() {
  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/master-vendors`),
  );
}

export async function listVendors({ status = "", query = "" } = {}) {
  return parseResponse(
    await fetch(withQuery("/api/v1/vendors", { status, query })),
  );
}

export async function extractDocuments(files) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));

  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/documents/extract`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function processVendor({ fields, files }) {
  const form = new FormData();
  Object.entries(fields || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      form.append(key, String(value));
    }
  });
  files.forEach((file) => form.append("files", file));

  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/vendors/process`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function uploadVendorDocuments(vendorId, files) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));

  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/vendors/${vendorId}/documents`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function getReviewQueue() {
  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/vendors/review-queue`),
  );
}

export async function getVendor(vendorId) {
  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/vendors/${vendorId}`),
  );
}

export async function reviewVendor(vendorId, body) {
  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/vendors/${vendorId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function getAuditEvents({ query = "", eventType = "" } = {}) {
  return parseResponse(
    await fetch(withQuery("/api/v1/audit-events", {
      query,
      event_type: eventType,
    })),
  );
}

export { API_BASE_URL };
