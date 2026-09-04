const PLUGIN_ID = "pex-opencode-plugin"
const PLUGIN_VERSION = "1.0.1"
const CACHE_MS = 250
const HEARTBEAT_MS = 10_000
const MAX_TOKEN_CHARS = 512
const MAX_REQUEST_BYTES = 1_048_576
const MAX_RESPONSE_BYTES = 262_144
const MAX_CACHE_ENTRIES = 256
const MAX_INSTRUCTIONS_CHARS = 32_768

function bridgeUrl() {
  const raw = process.env.PEX_BRIDGE_URL || "http://127.0.0.1:7420"
  const parsed = new URL(raw)
  if (
    parsed.protocol !== "http:" ||
    !["127.0.0.1", "localhost", "::1", "[::1]"].includes(parsed.hostname) ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    !["", "/"].includes(parsed.pathname)
  ) {
    throw new Error("PEX_BRIDGE_URL must be a bare loopback HTTP origin")
  }
  if (parsed.hostname === "localhost") parsed.hostname = "127.0.0.1"
  return parsed.origin
}

function validToken(raw) {
  const token = String(raw || "").trim()
  if (!token || token.length > MAX_TOKEN_CHARS || !/^[\x21-\x7e]+$/.test(token)) return ""
  return token
}

function strictJsonParse(text) {
  const source = String(text)
  let index = 0
  let nodes = 0

  function whitespace() {
    while (index < source.length && /[\t\n\r ]/.test(source[index])) index += 1
  }

  function stringToken() {
    const start = index
    if (source[index] !== '"') throw new Error("invalid JSON string")
    index += 1
    while (index < source.length) {
      const char = source[index]
      if (char === '"') {
        index += 1
        return JSON.parse(source.slice(start, index))
      }
      if (char === "\\") index += 1
      index += 1
    }
    throw new Error("unterminated JSON string")
  }

  function value(depth) {
    nodes += 1
    if (depth > 32 || nodes > 4096) throw new Error("JSON structure exceeded limit")
    whitespace()
    const char = source[index]
    if (char === "{") return object(depth)
    if (char === "[") return array(depth)
    if (char === '"') {
      stringToken()
      return
    }
    const start = index
    while (index < source.length && !/[\t\n\r ,\]}]/.test(source[index])) index += 1
    if (index === start) throw new Error("invalid JSON value")
    const scalar = source.slice(start, index)
    if (/^-?(?:0|[1-9])/.test(scalar) && !Number.isFinite(Number(scalar))) {
      throw new Error("non-finite JSON number")
    }
  }

  function object(depth) {
    index += 1
    whitespace()
    const keys = new Set()
    if (source[index] === "}") {
      index += 1
      return
    }
    while (index < source.length) {
      whitespace()
      const key = stringToken()
      if (keys.has(key)) throw new Error("duplicate JSON object key")
      keys.add(key)
      whitespace()
      if (source[index] !== ":") throw new Error("invalid JSON object")
      index += 1
      value(depth + 1)
      whitespace()
      if (source[index] === "}") {
        index += 1
        return
      }
      if (source[index] !== ",") throw new Error("invalid JSON object")
      index += 1
    }
    throw new Error("unterminated JSON object")
  }

  function array(depth) {
    index += 1
    whitespace()
    if (source[index] === "]") {
      index += 1
      return
    }
    while (index < source.length) {
      value(depth + 1)
      whitespace()
      if (source[index] === "]") {
        index += 1
        return
      }
      if (source[index] !== ",") throw new Error("invalid JSON array")
      index += 1
    }
    throw new Error("unterminated JSON array")
  }

  value(0)
  whitespace()
  if (index !== source.length) throw new Error("trailing JSON data")
  return JSON.parse(source)
}

function hookToken() {
  return validToken(process.env.PEX_OPENCODE_HOOK_TOKEN || process.env.PEX_HOOK_TOKEN)
}

function abortSignal(ms) {
  const controller = new AbortController()
  setTimeout(() => {
    try {
      controller.abort()
    } catch {
      // Already aborted or unsupported.
    }
  }, ms)
  return controller.signal
}

async function boundedJson(response) {
  const declared = Number(response.headers.get("content-length") || 0)
  if (declared > MAX_RESPONSE_BYTES) throw new Error("PEX bridge response exceeded limit")
  if (!response.body) return {}
  const reader = response.body.getReader()
  const chunks = []
  let total = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      total += value.byteLength
      if (total > MAX_RESPONSE_BYTES) throw new Error("PEX bridge response exceeded limit")
      chunks.push(value)
    }
  } catch (error) {
    await reader.cancel().catch(() => {})
    throw error
  }
  const bytes = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    bytes.set(chunk, offset)
    offset += chunk.byteLength
  }
  const parsed = strictJsonParse(new TextDecoder("utf-8", { fatal: true }).decode(bytes))
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("PEX bridge returned a non-object response")
  }
  return parsed
}

function boundedStrings(value, maxItems = 128, maxChars = 128) {
  if (!Array.isArray(value) || value.length > maxItems) return []
  return value
    .filter(
      (item) =>
        typeof item === "string" &&
        item.length <= maxChars &&
        !/[\x00-\x1f\x7f]/.test(item),
    )
    .map((item) => item.trim())
    .filter(Boolean)
}

function runtimeValue(raw) {
  const instructions = typeof raw.system_instructions === "string"
    ? raw.system_instructions.trim()
    : ""
  if (instructions.length > MAX_INSTRUCTIONS_CHARS || instructions.includes("\x00")) {
    throw new Error("PEX overlay instructions exceeded limit")
  }
  return {
    active: raw.active === true,
    system_instructions: instructions,
    overlay_ids: boundedStrings(raw.overlay_ids, 64, 128),
    disabled_tools: boundedStrings(raw.disabled_tools),
  }
}

function normalized(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "")
}

let sharedLastHeartbeat = 0

export const PexPlugin = async ({ directory }) => {
  let url
  try {
    url = bridgeUrl()
  } catch {
    // Invalid local configuration must not prevent OpenCode from starting.
    return {}
  }
  const safeDirectory =
    typeof directory === "string" &&
    directory.length <= 4096 &&
    !/[\x00-\x1f\x7f]/.test(directory)
      ? directory
      : ""
  const cache = new Map()
  let boundSession = ""

  async function request(path, init = {}) {
    if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//") || path.length > 8192) {
      throw new Error("PEX bridge path is unsafe")
    }
    const token = hookToken()
    if (!token) throw new Error("PEX scoped OpenCode credential is unavailable")
    if (typeof init.body === "string" && new TextEncoder().encode(init.body).byteLength > MAX_REQUEST_BYTES) {
      throw new Error("PEX bridge request exceeded limit")
    }
    const response = await fetch(`${url}${path}`, {
      ...init,
      headers: {
        ...(init.headers || {}),
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      signal: abortSignal(8000),
    })
    if (!response.ok) throw new Error(`PEX bridge returned HTTP ${response.status}`)
    return boundedJson(response)
  }

  async function heartbeat(sessionID = "") {
    const key = String(sessionID || "")
    if (key && (key.length > 512 || /[\x00-\x20\x7f]/.test(key))) {
      throw new Error("OpenCode session id is unsafe")
    }
    const now = Date.now()
    if (now - sharedLastHeartbeat < HEARTBEAT_MS && (!key || key === boundSession)) return
    await request("/v1/adapters/opencode/plugin-heartbeat", {
      method: "POST",
      body: JSON.stringify({
        source: PLUGIN_ID,
        version: PLUGIN_VERSION,
        directory: safeDirectory,
        ...(key ? { session_id: key } : {}),
      }),
    })
    if (key) boundSession = key
    sharedLastHeartbeat = now
  }

  async function runtime(sessionID, force = false) {
    const key = String(sessionID || "")
    if (!key || key.length > 512 || /[\x00-\x20\x7f]/.test(key)) return { active: false }
    await heartbeat(key)
    const cached = cache.get(key)
    if (!force && cached && Date.now() - cached.at < CACHE_MS) return cached.value
    const value = runtimeValue(
      await request(`/v1/sessions/${encodeURIComponent(`opencode:${key}`)}/overlay-runtime`),
    )
    cache.delete(key)
    cache.set(key, { at: Date.now(), value })
    while (cache.size > MAX_CACHE_ENTRIES) cache.delete(cache.keys().next().value)
    return value
  }

  // Do not await bridge I/O here: OpenCode serve holds the session lock during
  // plugin setup. Heartbeat from overlay hooks after the worker has a session.
  setTimeout(() => {
    void heartbeat().catch(() => {})
  }, 50)

  return {
    event: async () => {},

    "chat.message": async (input) => {
      const sessionID = typeof input?.sessionID === "string" ? input.sessionID : ""
      if (!sessionID) return
      try {
        await heartbeat(sessionID)
      } catch {
        // Binding must not block the worker turn.
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      let overlay
      try {
        overlay = await runtime(input.sessionID)
      } catch {
        return
      }
      const instructions = String(overlay.system_instructions || "").trim()
      if (!overlay.active || !instructions) return
      const marker = `[PEX ephemeral overlay: ${overlay.overlay_ids.join(", ")}]`
      const block = `${marker}\n${instructions}`
      if (!Array.isArray(output.system)) return
      if (output.system.length === 0) output.system.push(block)
      else if (
        typeof output.system[0] === "string" &&
        output.system[0].length + block.length + 2 <= MAX_RESPONSE_BYTES
      ) {
        output.system[0] = `${output.system[0]}\n\n${block}`
      }
    },

    "tool.execute.before": async (input) => {
      let overlay
      try {
        overlay = await runtime(input.sessionID, true)
      } catch {
        return
      }
      const tool =
        typeof input.tool === "string" &&
        input.tool.length <= 512 &&
        !/[\x00-\x1f\x7f]/.test(input.tool)
          ? input.tool
          : ""
      if (!tool) return
      const disabled = new Set((overlay.disabled_tools || []).map(normalized))
      if (disabled.has(normalized(tool))) {
        throw new Error(
          `PEX session overlay ${overlay.overlay_ids.join(", ")} disabled tool ${tool}`,
        )
      }
    },
  }
}
