/**
 * VEO License Validation Worker — Cloudflare Workers (Backup)
 * ===========================================================
 * Redundant backup for Vercel endpoint.
 * Same logic: receive raw hw components → compute machine_id → verify.
 * 
 * Uses Firebase Auth REST API to sign in as bot user,
 * then Firestore REST API to read _lic docs (requires role='bot' claim).
 *
 * Deploy: wrangler deploy
 * Test:   curl https://veo-license.workers.dev/api/license/validate
 *
 * Environment variables (wrangler.toml secrets):
 *   FIREBASE_BOT_EMAIL, FIREBASE_BOT_PASSWORD,
 *   FIREBASE_PRIMARY_API_KEY, FIREBASE_BACKUP_API_KEY,
 *   FIREBASE_PRIMARY_PROJECT, FIREBASE_BACKUP_PROJECT
 */

// ── Constants ──────────────────────────────────────────────────

const FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword";
const FIRESTORE_BASE = "https://firestore.googleapis.com/v1";

const HMAC_DERIVE_KEY = "veo_rest_derive_2026";
const HMAC_DERIVE_SUFFIX = "||REST_HMAC";

const APP_COLLECTIONS = {
  veo: { lic: "_lic", blocked: "_blocked_machines", mid_to_key: "_mid_to_key" },
  grok: { lic: "_lic_grok", blocked: "_grok_blocked_machines", mid_to_key: "_grok_mid_to_key" },
};

// ── Cached auth token (per isolate) ────────────────────────────

let cachedTokens = {};  // { projectKey: { idToken, expiry } }

// ── Crypto helpers ─────────────────────────────────────────────

async function sha256hex(text) {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

async function hmacSha256(key, message) {
  const encoder = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw", encoder.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, encoder.encode(message));
  return Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

// ── Firebase Auth ──────────────────────────────────────────────

async function getIdToken(apiKey, email, password) {
  const cacheKey = apiKey;
  const cached = cachedTokens[cacheKey];
  if (cached && Date.now() < cached.expiry - 60000) {
    return cached.idToken;
  }

  const resp = await fetch(`${FIREBASE_AUTH_URL}?key=${apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      returnSecureToken: true,
    }),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(`Firebase Auth failed: ${err?.error?.message || resp.status}`);
  }

  const data = await resp.json();
  cachedTokens[cacheKey] = {
    idToken: data.idToken,
    expiry: Date.now() + (parseInt(data.expiresIn || "3600") * 1000),
  };
  return data.idToken;
}

// ── Firestore REST API ─────────────────────────────────────────

function parseFirestoreValue(val) {
  if ("stringValue" in val) return val.stringValue;
  if ("integerValue" in val) return parseInt(val.integerValue);
  if ("booleanValue" in val) return val.booleanValue;
  if ("doubleValue" in val) return val.doubleValue;
  if ("timestampValue" in val) return val.timestampValue;
  if ("nullValue" in val) return null;
  if ("mapValue" in val) {
    const fields = val.mapValue.fields || {};
    const result = {};
    for (const [k, v] of Object.entries(fields)) {
      result[k] = parseFirestoreValue(v);
    }
    return result;
  }
  return null;
}

function parseFirestoreDoc(doc) {
  if (!doc || !doc.fields) return null;
  const result = {};
  for (const [k, v] of Object.entries(doc.fields)) {
    result[k] = parseFirestoreValue(v);
  }
  return result;
}

async function readDoc(project, collection, docId, token) {
  const url = `${FIRESTORE_BASE}/projects/${project}/databases/(default)/documents/${collection}/${docId}`;
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (resp.status === 404) return null;
  if (!resp.ok) return null;
  return parseFirestoreDoc(await resp.json());
}

function toFirestoreValue(val) {
  if (val === null || val === undefined) return { nullValue: null };
  if (typeof val === "boolean") return { booleanValue: val };
  if (typeof val === "number") return Number.isInteger(val) ? { integerValue: String(val) } : { doubleValue: val };
  if (typeof val === "string") return { stringValue: val };
  if (typeof val === "object") {
    const fields = {};
    for (const [k, v] of Object.entries(val)) {
      fields[k] = toFirestoreValue(v);
    }
    return { mapValue: { fields } };
  }
  return { stringValue: String(val) };
}

async function writeDoc(project, collection, docId, data, token) {
  const url = `${FIRESTORE_BASE}/projects/${project}/databases/(default)/documents/${collection}/${docId}`;
  const fields = {};
  for (const [k, v] of Object.entries(data)) {
    fields[k] = toFirestoreValue(v);
  }
  const resp = await fetch(`${url}?updateMask.fieldPaths=${Object.keys(data).join("&updateMask.fieldPaths=")}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ fields }),
  });
  return resp.ok;
}

// ── Hardware Verification ──────────────────────────────────────

async function computeMachineId(hw) {
  const combined = [
    hw.cpu_id || "",
    hw.mb_serial || "",
    hw.mb_uuid || "",
    hw.bios_serial || "",
    hw.disk_serial || "",
  ].join("|");
  return sha256hex(combined);
}

async function hashComponent(value) {
  const full = await sha256hex(value);
  return full.substring(0, 32);
}

async function verifyHwComponents(hw, storedHw) {
  for (const key of ["cpu_id", "mb_serial", "mb_uuid", "bios_serial", "disk_serial"]) {
    const sentValue = hw[key] || "";
    const storedHash = storedHw[key] || "";
    if (!storedHash) continue;
    const computed = await hashComponent(sentValue);
    if (computed !== storedHash) return false;
  }
  return true;
}

// ── HMAC Token Verification ────────────────────────────────────

async function verifyRequestToken(machineId, token) {
  if (!token || !token.includes(":")) return false;
  try {
    const [tsBucket, sig] = token.split(":", 2);
    const currentBucket = Math.floor(Date.now() / 1000 / 300);
    const tokenBucket = parseInt(tsBucket);
    const ageBuckets = currentBucket - tokenBucket;
    if (ageBuckets < 0 || ageBuckets > 6) return false;  // 30 min max

    const derivedKey = await hmacSha256(HMAC_DERIVE_KEY, machineId + HMAC_DERIVE_SUFFIX);
    const msg = `${machineId}${tsBucket}`;
    const expected = (await hmacSha256(derivedKey, msg)).substring(0, 32);
    return sig === expected;
  } catch {
    return false;
  }
}

// ── Core Validation Logic ──────────────────────────────────────

async function handleValidate(body, env) {
  const action = body.action || "validate";
  const hw = body.hw || {};
  const app = (body.app || "veo").toLowerCase();
  const token = body._token || "";

  // Route restore action (no license_key required)
  if (action === "restore") {
    return handleRestore(body, env);
  }

  const licenseKey = (body.license_key || "").trim();
  if (!licenseKey) return { valid: false, error: "missing_license_key" };
  if (!(app in APP_COLLECTIONS)) return { valid: false, error: "invalid_app" };

  // Validate hardware components
  for (const key of ["cpu_id", "mb_serial", "mb_uuid", "bios_serial", "disk_serial"]) {
    const val = hw[key] || "";
    if (!val || typeof val !== "string" || val.length < 2) {
      return { valid: false, error: `missing_hw_${key}` };
    }
  }

  // Compute machine_id
  const computedMid = await computeMachineId(hw);

  // Verify HMAC token (MANDATORY)
  if (!(await verifyRequestToken(computedMid, token))) {
    return { valid: false, error: "invalid_token" };
  }

  // Unified failure response (prevents key enumeration)
  const FAIL = { valid: false, error: "validation_failed" };

  // Sign in as bot to both projects
  const primaryToken = await getIdToken(
    env.FIREBASE_PRIMARY_API_KEY, env.FIREBASE_BOT_EMAIL, env.FIREBASE_BOT_PASSWORD
  );

  const collections = APP_COLLECTIONS[app];

  // Check blocked
  const blocked = await readDoc(env.FIREBASE_PRIMARY_PROJECT, collections.blocked, computedMid, primaryToken);
  if (blocked && blocked.blocked) return FAIL;

  // Read license (primary, then backup)
  let licData = await readDoc(env.FIREBASE_PRIMARY_PROJECT, collections.lic, licenseKey, primaryToken);

  if (!licData && env.FIREBASE_BACKUP_API_KEY) {
    try {
      const backupToken = await getIdToken(
        env.FIREBASE_BACKUP_API_KEY, env.FIREBASE_BOT_EMAIL, env.FIREBASE_BOT_PASSWORD
      );
      licData = await readDoc(env.FIREBASE_BACKUP_PROJECT, collections.lic, licenseKey, backupToken);
    } catch { /* backup unavailable */ }
  }

  if (!licData) return FAIL;

  // Check revoked
  if (licData._st === "r" || licData.revoked) return FAIL;

  // Check expiry
  const expStr = licData._exp || licData.expires || "";
  if (expStr) {
    try {
      const expDate = new Date(expStr);
      if (expDate < new Date()) return FAIL;
    } catch { /* ignore parse errors */ }
  }

  // Machine ID verification
  const storedMid = (licData._mid || licData.machine_id || "").toLowerCase();
  if (storedMid && storedMid !== computedMid) return FAIL;

  // Hardware component verification
  const storedHw = licData._hw || {};
  if (storedHw && Object.keys(storedHw).length > 0) {
    if (!(await verifyHwComponents(hw, storedHw))) return FAIL;
  } else if (storedMid === computedMid) {
    // First-time binding: store hashed hw components
    const hwToStore = {};
    for (const key of ["cpu_id", "mb_serial", "mb_uuid", "bios_serial", "disk_serial"]) {
      hwToStore[key] = await hashComponent(hw[key]);
    }
    try {
      await writeDoc(env.FIREBASE_PRIMARY_PROJECT, collections.lic, licenseKey, {
        _hw: hwToStore,
        _hw_bound_at: new Date().toISOString(),
      }, primaryToken);
    } catch { /* non-critical */ }
  }

  // Build response
  const tierCode = licData._t || licData.tier || "TRIA";
  const role = licData._role || licData.role || 1;
  const clientName = licData._cn || licData.client_name || "";
  const lim = licData._lim;

  const response = {
    valid: true,
    tier: tierCode,
    role,
    expires: expStr,
    client_name: clientName,
    machine_id: computedMid,
    _hw_bound: true,
  };
  if (lim) response._lim = lim;

  return response;
}


// ── Restore by Machine ID ──────────────────────────────────────

async function handleRestore(body, env) {
  const hw = body.hw || {};
  const app = (body.app || "veo").toLowerCase();
  const token = body._token || "";

  if (!(app in APP_COLLECTIONS)) return { found: false, error: "invalid_app" };

  // Validate hardware components
  for (const key of ["cpu_id", "mb_serial", "mb_uuid", "bios_serial", "disk_serial"]) {
    const val = hw[key] || "";
    if (!val || typeof val !== "string" || val.length < 2) {
      return { found: false, error: `missing_hw_${key}` };
    }
  }

  const computedMid = await computeMachineId(hw);

  if (!(await verifyRequestToken(computedMid, token))) {
    return { found: false, error: "invalid_token" };
  }

  // Sign in as bot
  const primaryToken = await getIdToken(
    env.FIREBASE_PRIMARY_API_KEY, env.FIREBASE_BOT_EMAIL, env.FIREBASE_BOT_PASSWORD
  );

  const collections = APP_COLLECTIONS[app];

  // Check blocked
  const blocked = await readDoc(env.FIREBASE_PRIMARY_PROJECT, collections.blocked, computedMid, primaryToken);
  if (blocked && blocked.blocked) return { found: false, error: "machine_blocked" };

  // Read _mid_to_key/{machine_id} (app-specific collection)
  const midData = await readDoc(env.FIREBASE_PRIMARY_PROJECT, collections.mid_to_key, computedMid, primaryToken);
  if (!midData) return { found: false };

  const licenseKey = midData.key || "";
  if (!licenseKey || licenseKey === "****") return { found: false };

  // Read license doc for full info
  const licData = await readDoc(env.FIREBASE_PRIMARY_PROJECT, collections.lic, licenseKey, primaryToken);
  if (!licData) return { found: false };

  if (licData._st === "r" || licData.revoked) return { found: false, error: "license_revoked" };

  return {
    found: true,
    key: licenseKey,
    tier: licData._t || licData.tier || "TRIA",
    role: licData._role || licData.role || 1,
    expires: licData._exp || licData.expires || "",
    client_name: licData._cn || licData.client_name || "",
  };
}

// ── Worker Entry Point ─────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS headers
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Api-Secret",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // Health check
    if (request.method === "GET") {
      return Response.json(
        { status: "ok", service: "veo-license-validate-cf" },
        { headers: { ...corsHeaders, "Cache-Control": "no-store" } }
      );
    }

    // Only POST for validation
    if (request.method !== "POST") {
      return Response.json(
        { valid: false, error: "method_not_allowed" },
        { status: 405, headers: corsHeaders }
      );
    }

    try {
      // Body size check (10KB max)
      const contentLength = parseInt(request.headers.get("content-length") || "0");
      if (contentLength > 10000) {
        return Response.json(
          { valid: false, error: "body_too_large" },
          { status: 413, headers: corsHeaders }
        );
      }

      const body = await request.json();
      const result = await handleValidate(body, env);

      return Response.json(result, {
        headers: { ...corsHeaders, "Cache-Control": "no-store" },
      });
    } catch (e) {
      console.error("License validation error:", e);
      return Response.json(
        { valid: false, error: "internal_error" },
        { status: 500, headers: corsHeaders }
      );
    }
  },
};
