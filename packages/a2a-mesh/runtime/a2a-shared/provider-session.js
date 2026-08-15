// ============================================
// Provider Session Contract — provider-agnostic runtime session metadata
// ============================================

function asRecord(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function cleanString(value) {
  if (value === undefined || value === null) return undefined;
  const text = String(value).trim();
  return text || undefined;
}

function firstValue(...values) {
  for (const value of values) {
    const cleaned = cleanString(value);
    if (cleaned !== undefined) return cleaned;
  }
  return undefined;
}

export function extractProviderSession(...sources) {
  const session = {};

  for (const source of sources) {
    const data = asRecord(source);
    const nested = asRecord(data.providerSession);

    session.providerSessionId = firstValue(
      data.providerSessionId,
      data.provider_session_id,
      nested.providerSessionId,
      nested.provider_session_id,
      nested.sessionId,
      nested.id,
      session.providerSessionId,
    );

    session.providerSessionKey = firstValue(
      data.providerSessionKey,
      data.provider_session_key,
      nested.providerSessionKey,
      nested.provider_session_key,
      nested.key,
      session.providerSessionKey,
    );

    session.runtime = firstValue(
      data.runtime,
      data.providerRuntime,
      data.provider_runtime,
      nested.runtime,
      nested.providerRuntime,
      nested.provider_runtime,
      session.runtime,
    );
  }

  return Object.fromEntries(Object.entries(session).filter(([, value]) => value !== undefined));
}

export function buildProviderSessionKey({ sessionId, agentId, runtime } = {}) {
  const cleanSessionId = cleanString(sessionId);
  const cleanAgentId = cleanString(agentId);
  const cleanRuntime = cleanString(runtime);
  if (!cleanSessionId || !cleanAgentId || !cleanRuntime) return undefined;
  return `mesh:${cleanSessionId}:agent:${cleanAgentId}:runtime:${cleanRuntime}`;
}

export function mergeProviderSessionMetadata(metadata = {}, { sessionId, agentId } = {}) {
  const base = asRecord(metadata);
  const providerSession = extractProviderSession(base);

  if (!providerSession.providerSessionKey) {
    providerSession.providerSessionKey = buildProviderSessionKey({
      sessionId,
      agentId,
      runtime: providerSession.runtime,
    });
  }

  const cleanedProviderSession = Object.fromEntries(
    Object.entries(providerSession).filter(([, value]) => value !== undefined),
  );
  if (Object.keys(cleanedProviderSession).length === 0) return { ...base };

  return {
    ...base,
    ...cleanedProviderSession,
    providerSession: {
      ...asRecord(base.providerSession),
      ...cleanedProviderSession,
    },
  };
}

export function mergeRequestTaskMetadata(request = {}, fallbackMetadata = {}) {
  const body = asRecord(request);
  const metadata = {
    ...asRecord(fallbackMetadata),
    ...asRecord(body.metadata),
  };

  const sessionId = firstValue(body.sessionId, metadata.sessionId);
  if (sessionId) metadata.sessionId = sessionId;

  const providerSession = extractProviderSession(metadata, body);
  return mergeProviderSessionMetadata(
    { ...metadata, ...providerSession },
    {
      sessionId,
      agentId: firstValue(body.agentId, body.agent, metadata.agentId, metadata.agent),
    },
  );
}

