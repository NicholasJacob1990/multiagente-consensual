import { createHash, randomUUID } from 'crypto';

export function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]),
    );
  }
  return value;
}

/**
 * Build retry-stable request IDs without conflating independent MCP clients.
 *
 * Identical requests made through the same bridge process reuse an ID only
 * during a short sliding window. A different bridge process gets a different
 * random scope unless the host explicitly supplies A2A_MESH_BRIDGE_SESSION_ID.
 */
export function createStableRequestIdFactory({
  scope = `bridge-${process.pid}-${randomUUID()}`,
  retryWindowMs = 60_000,
  maxEntries = 1000,
  now = () => Date.now(),
  nonce = () => randomUUID(),
} = {}) {
  const windowMs = Math.max(1_000, Number.parseInt(String(retryWindowMs), 10) || 60_000);
  const capacity = Math.max(16, Number.parseInt(String(maxEntries), 10) || 1000);
  const cache = new Map();

  return (method, params) => {
    const timestamp = now();
    const material = JSON.stringify({ method, params: canonicalValue(params) });
    const materialHash = createHash('sha256').update(material).digest('hex');
    const cached = cache.get(materialHash);
    if (cached && timestamp < cached.expiresAt) {
      cache.delete(materialHash);
      cache.set(materialHash, cached);
      return cached.requestId;
    }
    if (cached) cache.delete(materialHash);

    const requestId = `mcp-${createHash('sha256')
      .update(JSON.stringify({ materialHash, scope, nonce: nonce() }))
      .digest('hex')
      .slice(0, 32)}`;
    cache.set(materialHash, { requestId, expiresAt: timestamp + windowMs });
    while (cache.size > capacity) cache.delete(cache.keys().next().value);
    return requestId;
  };
}
