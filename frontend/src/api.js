const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function parseResponse(response) {
  if (response.ok) {
    if (response.status === 204) return null;
    return response.json();
  }

  let message = `Request failed with status ${response.status}`;
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") message = payload.detail;
    else if (payload?.detail) message = JSON.stringify(payload.detail);
  } catch {
    // Keep the generic HTTP error.
  }
  throw new Error(message);
}

export async function getHealth() {
  return parseResponse(await fetch(`${API_BASE_URL}/health`));
}

export async function processVendor({ legalName, files }) {
  const form = new FormData();
  form.append("legal_name", legalName || "");
  files.forEach((file) => form.append("files", file));

  return parseResponse(
    await fetch(`${API_BASE_URL}/api/v1/vendors/process`, {
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

export { API_BASE_URL };
