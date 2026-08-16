// ============================================
// Mesh Calls — A2A inter-agent communication
// ============================================
// Uses SSE streaming (/tasks/sendSubscribe) for real-time event forwarding.

import { randomUUID } from 'crypto';
import { A2A_PROTOCOL_VERSION, A2A_VERSION_HEADER } from './protocol.js';
import { enrichPromptIfContinuation } from './mesh-continuation.js';
import { extractProviderSession, mergeProviderSessionMetadata } from './provider-session.js';
import { cancelRemoteTask, recoverRemoteTask } from './remote-task-control.js';

function formatError(err) {
  return err instanceof Error ? err.message : String(err);
}

function normalizePositiveInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeTimeoutMs(value, fallback, { min = 1000, max = 3600000 } = {}) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
}

function normalizeMeshChain(meshChain) {
  if (!Array.isArray(meshChain)) return [];
  const normalized = [];
  for (const entry of meshChain) {
    if (typeof entry !== 'string' || !entry) continue;
    if (normalized[normalized.length - 1] !== entry) {
      normalized.push(entry);
    }
  }
  return normalized;
}

/**
 * Detects whether a string returned by executeA2ACall / executeA2ABroadcast
 * is a mesh-level error rather than an actual agent response. Use this at
 * every consumer site (consensus, ensemble, debate) so error strings don't
 * get treated as content and poison downstream parsers.
 */
export function isMeshErrorText(value) {
  // Match only the exact shapes mesh-calls produces:
  //   Error: ...           (depth/loop/self-call)
  //   Error from <agent>:  (peer call failure)
  //   Unknown agent: ...
  //   No response received from agent
  // The bare \bError\b form was intentionally dropped — it false-positived on
  // substantive content like "Error handling in Python is done with try/except".
  return /^(Error\s+from\s|Error:|Unknown agent:|No response received from agent)/i.test(String(value || '').trim());
}

function appendSelfToMeshChain(meshChain, selfId) {
  const normalized = normalizeMeshChain(meshChain);
  if (normalized[normalized.length - 1] !== selfId) {
    normalized.push(selfId);
  }
  return normalized;
}

function buildForwardedMetadata(base, context, input, targetAgent) {
  const providerSession = extractProviderSession(input, context);
  return mergeProviderSessionMetadata(
    { ...base, ...providerSession },
    {
      sessionId: context.sessionId || base.sessionId,
      agentId: targetAgent,
    },
  );
}

class PeerRateLimiter {
  constructor({ windowMs = 60000, maxRequests = 30 } = {}) {
    this.windowMs = windowMs;
    this.maxRequests = maxRequests;
    this.requestsByPeer = new Map();
  }

  allow(peerId) {
    const now = Date.now();
    const windowStart = now - this.windowMs;
    const requests = this.requestsByPeer.get(peerId) || [];
    while (requests.length && requests[0] < windowStart) requests.shift();
    if (requests.length >= this.maxRequests) {
      this.requestsByPeer.set(peerId, requests);
      return false;
    }
    requests.push(now);
    this.requestsByPeer.set(peerId, requests);
    return true;
  }
}

class PeerCircuitBreaker {
  constructor({ failureThreshold = 5, openMs = 30000 } = {}) {
    this.failureThreshold = failureThreshold;
    this.openMs = openMs;
    this.stateByPeer = new Map();
  }

  _state(peerId) {
    if (!this.stateByPeer.has(peerId)) {
      this.stateByPeer.set(peerId, {
        state: 'CLOSED',
        failures: 0,
        openedAt: 0,
        probeInFlight: false,
      });
    }
    return this.stateByPeer.get(peerId);
  }

  canRequest(peerId) {
    const now = Date.now();
    const entry = this._state(peerId);
    if (entry.state === 'CLOSED') return true;

    if (entry.state === 'OPEN') {
      if (now - entry.openedAt < this.openMs) return false;
      entry.state = 'HALF_OPEN';
      entry.probeInFlight = false;
    }

    if (entry.state === 'HALF_OPEN') {
      if (entry.probeInFlight) return false;
      entry.probeInFlight = true;
      return true;
    }

    return true;
  }

  onSuccess(peerId) {
    const entry = this._state(peerId);
    entry.state = 'CLOSED';
    entry.failures = 0;
    entry.probeInFlight = false;
  }

  onFailure(peerId) {
    const now = Date.now();
    const entry = this._state(peerId);
    entry.probeInFlight = false;

    if (entry.state === 'HALF_OPEN') {
      entry.state = 'OPEN';
      entry.openedAt = now;
      return;
    }

    entry.failures += 1;
    if (entry.failures >= this.failureThreshold) {
      entry.state = 'OPEN';
      entry.openedAt = now;
    }
  }

  onNeutral(peerId) {
    const entry = this._state(peerId);
    // A caller cancellation is not evidence about peer health. If it happened
    // during the single HALF_OPEN probe, release the probe slot for the next
    // request instead of wedging the breaker indefinitely.
    entry.probeInFlight = false;
  }

  isProbeInFlight(peerId) {
    const entry = this._state(peerId);
    return entry.state === 'HALF_OPEN' && entry.probeInFlight;
  }
}

/**
 * Create mesh caller with A2A call, broadcast, and depth filtering.
 *
 * @param {Object} config
 * @param {string} config.selfId - This server's ID
 * @param {Object} config.peers - { agentId: url } map (excludes self)
 * @param {number} config.maxDepth - Max mesh recursion depth
 * @param {Object} [config.meshBus] - MeshEventBus instance (optional)
 * @param {string} [config.selfUrl] - This server's own URL (enables self-calls for debate/consensus)
 * @param {Object} [config.peerDiscovery] - PeerDiscovery instance for status-aware routing (optional)
 * @returns {{ executeA2ACall, executeA2ABroadcast, getToolsForDepth }}
 */
export function createMeshCaller({ selfId, peers, maxDepth, meshBus, meshStore = null, authToken = '', selfUrl = '', peerDiscovery = null }) {
  const rateLimiter = new PeerRateLimiter({
    windowMs: parseInt(process.env.A2A_PEER_RATE_WINDOW_MS || '60000', 10),
    maxRequests: parseInt(process.env.A2A_PEER_RATE_MAX_REQUESTS || '30', 10),
  });
  const circuitBreaker = new PeerCircuitBreaker({
    failureThreshold: parseInt(process.env.A2A_PEER_CB_FAILURE_THRESHOLD || '5', 10),
    openMs: parseInt(process.env.A2A_PEER_CB_OPEN_MS || '30000', 10),
  });
  const DEFAULT_CALL_TIMEOUT_MS = normalizePositiveInt(process.env.A2A_TIMEOUT_CALL_MS, 1800000); // 30 min per model call

  // Dedup cache applies only to complete task-dialogue turns. task-progress is
  // an exact delta stream and may legitimately repeat the same token.
  const CHUNK_DEDUP_MAX = normalizePositiveInt(process.env.A2A_CHUNK_DEDUP_MAX, 1000);
  const _chunkDedupCache = new Map();
  function chunkDedupSet(key, value) {
    if (_chunkDedupCache.has(key)) _chunkDedupCache.delete(key);
    else if (_chunkDedupCache.size >= CHUNK_DEDUP_MAX) {
      const oldest = _chunkDedupCache.keys().next().value;
      if (oldest !== undefined) _chunkDedupCache.delete(oldest);
    }
    _chunkDedupCache.set(key, value);
  }
  const MAX_SELF_CALL_DEPTH = normalizePositiveInt(process.env.A2A_MAX_SELF_CALL_DEPTH, 3);
  const PEER_RETRY_ATTEMPTS = normalizePositiveInt(process.env.A2A_PEER_RETRY_ATTEMPTS, 2);
  const PEER_RETRY_BASE_DELAY_MS = normalizePositiveInt(process.env.A2A_PEER_RETRY_BASE_DELAY_MS, 750);
  const PEER_RETRY_MAX_DELAY_MS = normalizePositiveInt(process.env.A2A_PEER_RETRY_MAX_DELAY_MS, 5000);
  const PEER_RETRY_JITTER_MS = Number.parseInt(String(process.env.A2A_PEER_RETRY_JITTER_MS ?? '250'), 10);

  function isRetryableHttpStatus(status) {
    return status === 408 || status === 425 || status === 429 || status >= 500;
  }

  function computeRetryDelayMs(retryIndex) {
    const exponential = Math.min(PEER_RETRY_MAX_DELAY_MS, PEER_RETRY_BASE_DELAY_MS * (2 ** Math.max(0, retryIndex - 1)));
    const jitterCap = Number.isFinite(PEER_RETRY_JITTER_MS) && PEER_RETRY_JITTER_MS > 0 ? PEER_RETRY_JITTER_MS : 0;
    const jitter = jitterCap > 0 ? Math.floor(Math.random() * (jitterCap + 1)) : 0;
    return Math.min(PEER_RETRY_MAX_DELAY_MS, exponential + jitter);
  }

  /**
   * Stream SSE from /tasks/sendSubscribe and collect result.
   * Emits real-time dialogue events to meshBus.
   */
  async function streamTaskAttempt(
    peerUrl,
    body,
    agent,
    parentTaskId,
    timeoutMs = DEFAULT_CALL_TIMEOUT_MS,
    { tripCircuit = true, signal: externalSignal } = {},
  ) {
    if (!rateLimiter.allow(agent)) {
      return { error: `Rate limit exceeded for ${agent}`, retryable: false };
    }
    if (!circuitBreaker.canRequest(agent)) {
      return { error: `Circuit breaker OPEN for ${agent}`, retryable: true };
    }
    const circuitProbe = circuitBreaker.isProbeInFlight(agent);
    const shouldRecordCircuitFailure = tripCircuit || circuitProbe;

    const controller = new AbortController();
    const deadline = Date.now() + timeoutMs;
    let remoteTaskId = null;
    let cancelPromise = null;
    let timedOut = false;
    let completedText = '';
    let checkpointAt = 0;
    let checkpointLength = 0;
    const checkpoint = (text = lastText, { complete = false, force = false } = {}) => {
      if (!meshStore?.upsertPartialSnapshot || !text) return;
      const now = Date.now();
      if (!force && now - checkpointAt < 1000 && text.length - checkpointLength < 4096) return;
      meshStore.upsertPartialSnapshot(
        parentTaskId,
        agent,
        String(text).slice(-200_000),
        { operation: 'stream', remoteTaskId, complete },
      );
      checkpointAt = now;
      checkpointLength = text.length;
    };
    const cancelKnownRemote = () => {
      if (remoteTaskId && !cancelPromise) {
        cancelPromise = cancelRemoteTask(peerUrl, remoteTaskId, { authToken });
      }
      return cancelPromise;
    };
    const abortFromCaller = () => {
      cancelKnownRemote();
      controller.abort(externalSignal?.reason || new Error('Task canceled by caller'));
    };
    if (externalSignal?.aborted) abortFromCaller();
    else externalSignal?.addEventListener('abort', abortFromCaller, { once: true });
    const timeout = setTimeout(() => {
      timedOut = true;
      cancelKnownRemote();
      controller.abort(new Error(`Timeout (${timeoutMs}ms)`));
    }, timeoutMs);
    let lastText = '';

    try {
      const resp = await fetch(`${peerUrl}/tasks/sendSubscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION,
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body,
        signal: controller.signal,
      });

      // Log peer protocol version for debugging (safe access — headers may be absent in mocks/tests)
      const peerVersion = resp.headers?.get?.(A2A_VERSION_HEADER) ?? null;
      if (peerVersion && peerVersion !== A2A_PROTOCOL_VERSION) {
        console.warn(`[mesh-calls] Peer ${agent} uses protocol version ${peerVersion} (ours: ${A2A_PROTOCOL_VERSION})`);
      }

      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        const retryable = isRetryableHttpStatus(resp.status);
        if (shouldRecordCircuitFailure && retryable) circuitBreaker.onFailure(agent);
        else if (!retryable) circuitBreaker.onSuccess(agent);
        return { error: `HTTP ${resp.status}: ${text.slice(0, 4000)}`, retryable };
      }

      let finalStatus = null;

      // Parse SSE stream
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let eventType = '';
      let eventData = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // keep incomplete line

        for (const rawLine of lines) {
          const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
          } else if (line === '' && eventData) {
            // End of SSE event — process it
            try {
              const data = JSON.parse(eventData);
              if (data.id) remoteTaskId = data.id;
              handleSSEEvent(eventType, data, agent, parentTaskId);

              if (eventType === 'task-status') {
                const state = data.status?.state;
                if (state === 'completed' || state === 'failed' || state === 'canceled') {
                  finalStatus = data;
                }
              }
              if (eventType === 'task-progress' && data.chunk) {
                const chunk = String(data.chunk);
                // task-progress is a delta in the local A2A contract. Append
                // byte-for-byte; repeated tokens are legitimate output.
                lastText += chunk;
                checkpoint();
              }
            } catch (err) {
              console.warn('[mesh-calls] Failed to parse SSE event from peer', {
                agent,
                parentTaskId,
                eventType: eventType || 'unknown',
                dataPreview: String(eventData).slice(0, 4000),
                error: formatError(err),
              });
            }
            eventType = '';
            eventData = '';
          } else if (line.startsWith(':')) {
            // Comment/heartbeat — ignore
          }
        }
      }

      // Extract response text from final status
      if (finalStatus) {
        const msg = finalStatus.status?.message;
        const finalState = finalStatus.status?.state;
        if (finalState === 'completed' && msg) {
          const text = msg.parts?.map(p => p.text).join('\n');
          if (text) {
            circuitBreaker.onSuccess(agent);
            completedText = text;
            checkpoint(text, { complete: true, force: true });
            return { response: text, remoteTaskId, retryable: false };
          }
        }
        if (finalState === 'failed' || finalState === 'canceled') {
          if (shouldRecordCircuitFailure && finalState === 'failed') circuitBreaker.onFailure(agent);
          else if (finalState === 'canceled') circuitBreaker.onNeutral(agent);
          checkpoint(lastText, { force: true });
          const errorText = msg?.parts?.[0]?.text || `Task ${finalState}`;
          return { error: errorText, partial: lastText || undefined, remoteTaskId, retryable: false };
        }
      }

      // The SSE transport may disappear while the remote CLI keeps running.
      // Recover by polling the already-created remote task instead of starting
      // a duplicate call with a new model session.
      if (remoteTaskId && Date.now() < deadline) {
        const recovered = await recoverRemoteTask(peerUrl, remoteTaskId, {
          authToken, deadline, signal: controller.signal,
          onPollError: (err) => {
            if (process.env.A2A_DEBUG === 'true') console.warn('[mesh-calls] Remote recovery poll failed', {
              agent, parentTaskId, remoteTaskId, error: formatError(err),
            });
          },
        });
        if (recovered.response) {
          circuitBreaker.onSuccess(agent);
          completedText = recovered.response;
          checkpoint(recovered.response, { complete: true, force: true });
        } else if (externalSignal?.aborted) {
          circuitBreaker.onNeutral(agent);
          await cancelKnownRemote();
        }
        else if (timedOut || /still running after the call timeout/i.test(recovered.error || '')) {
          await cancelKnownRemote();
          if (shouldRecordCircuitFailure) circuitBreaker.onFailure(agent);
          recovered.error = `Timeout (${timeoutMs}ms)`;
        } else if (shouldRecordCircuitFailure && !/canceled by caller/i.test(recovered.error || '')) {
          circuitBreaker.onFailure(agent);
        }
        if (!recovered.response) checkpoint(lastText, { force: true });
        return { ...recovered, partial: recovered.response ? undefined : lastText || undefined };
      }

      // Partial progress is diagnostic evidence, never a completed response.
      // Promoting it would let a dropped stream or killed model count as a
      // valid vote in debate/consensus/ensemble.
      if (lastText) {
        if (shouldRecordCircuitFailure) circuitBreaker.onFailure(agent);
        checkpoint(lastText, { force: true });
        return {
          error: 'Stream ended without a terminal task status',
          partial: lastText,
          remoteTaskId,
          retryable: !remoteTaskId,
        };
      }

      if (shouldRecordCircuitFailure) circuitBreaker.onFailure(agent);
      return { error: 'No response received from agent', remoteTaskId, retryable: !remoteTaskId };

    } catch (err) {
      if (externalSignal?.aborted) {
        await cancelKnownRemote();
        circuitBreaker.onNeutral(agent);
        checkpoint(lastText, { force: true });
        return { error: 'Task canceled by caller', partial: lastText || undefined, remoteTaskId, retryable: false };
      }
      if (timedOut) {
        await cancelKnownRemote();
        if (shouldRecordCircuitFailure) circuitBreaker.onFailure(agent);
        checkpoint(lastText, { force: true });
        return { error: `Timeout (${timeoutMs}ms)`, partial: lastText || undefined, remoteTaskId, retryable: false };
      }
      if (remoteTaskId && Date.now() < deadline) {
        const recovered = await recoverRemoteTask(peerUrl, remoteTaskId, {
          authToken, deadline, signal: controller.signal,
          onPollError: (pollError) => {
            if (process.env.A2A_DEBUG === 'true') console.warn('[mesh-calls] Remote recovery poll failed', {
              agent, parentTaskId, remoteTaskId, error: formatError(pollError),
            });
          },
        });
        if (recovered.response) {
          circuitBreaker.onSuccess(agent);
          completedText = recovered.response;
          checkpoint(recovered.response, { complete: true, force: true });
        } else if (externalSignal?.aborted) {
          circuitBreaker.onNeutral(agent);
          await cancelKnownRemote();
        }
        else if (timedOut || /still running after the call timeout/i.test(recovered.error || '')) {
          await cancelKnownRemote();
          if (shouldRecordCircuitFailure) circuitBreaker.onFailure(agent);
          recovered.error = `Timeout (${timeoutMs}ms)`;
        } else if (shouldRecordCircuitFailure && !/canceled by caller/i.test(recovered.error || '')) {
          circuitBreaker.onFailure(agent);
        }
        if (!recovered.response) checkpoint(lastText, { force: true });
        return { ...recovered, partial: recovered.response ? undefined : lastText || undefined };
      }
      if (shouldRecordCircuitFailure) circuitBreaker.onFailure(agent);
      if (err.name === 'AbortError') {
        return { error: `Timeout (${timeoutMs}ms)`, partial: lastText || undefined, remoteTaskId, retryable: false };
      }
      return { error: err.message, partial: lastText || undefined, remoteTaskId, retryable: !remoteTaskId };
    } finally {
      if (completedText) checkpoint(completedText, { complete: true, force: true });
      else if (lastText) checkpoint(lastText, { force: true });
      clearTimeout(timeout);
      externalSignal?.removeEventListener('abort', abortFromCaller);
    }
  }

  async function streamTask(peerUrl, body, agent, parentTaskId, timeoutMs = DEFAULT_CALL_TIMEOUT_MS, options = {}) {
    let lastResult = { error: 'Unknown stream error', retryable: false };
    let bestPartial = '';
    const attempts = Math.max(1, PEER_RETRY_ATTEMPTS);

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const isFinalAttempt = attempt >= attempts;
      const result = await streamTaskAttempt(
        peerUrl,
        body,
        agent,
        parentTaskId,
        timeoutMs,
        { tripCircuit: isFinalAttempt, signal: options.signal },
      );
      if (!result.error) return result;

      if ((result.partial || '').length > bestPartial.length) bestPartial = result.partial;
      lastResult = { ...result, partial: result.partial || bestPartial || undefined };
      if (isFinalAttempt || !result.retryable || result.remoteTaskId) return lastResult;

      const delayMs = computeRetryDelayMs(attempt);
      if (meshBus) {
        meshBus.publish({
          taskId: parentTaskId,
          type: 'dialogue',
          payload: {
            operation: 'stream',
            phase: 'retry',
            agent,
            role: 'system',
            text: `${agent} retry ${attempt + 1}/${attempts} em ${delayMs}ms após erro transitório: ${String(result.error).slice(0, 4000)}`,
          },
        });
      }
      await sleep(delayMs);
    }

    return lastResult;
  }

  /**
   * Handle incoming SSE event from remote agent — forward to local meshBus.
   *
   * 2026-04-30: dedup defensivo — observamos peer (Claude CLI) emitindo o
   * mesmo chunk de texto centenas de vezes em rajada (mesmo task gerou 907x,
   * 178x, 912x do mesmo texto). Tracking last-seen-text por (task, agent)
   * suprime o forward redundante. Causa-raiz no upstream ainda investigando.
   */
  function handleSSEEvent(eventType, data, agent, parentTaskId) {
    if (!meshBus) return;

    const dedupKey = `${parentTaskId}|${agent}`;
    const checkAndDedupe = (text) => {
      if (!text) return false;
      const prev = _chunkDedupCache.get(dedupKey);
      if (prev === text) return true; // skip — duplicate of last
      chunkDedupSet(dedupKey, text);
      return false;
    };

    switch (eventType) {
      case 'task-progress':
        meshBus.publish({
          taskId: parentTaskId,
          type: 'dialogue',
          payload: {
            operation: 'stream', phase: 'progress',
            agent, role: 'response',
            text: data.chunk || '',
            // Keep the non-durable contract when this dialogue is forwarded
            // again by an intermediate A2A server (A -> B -> C).
            transient: true,
          },
        }, { persist: false });
        break;

      case 'task-dialogue': {
        const transient = data.extra?.transient === true;
        // A transient dialogue is an exact token delta propagated through an
        // intermediate peer. Repeated adjacent tokens are content, not
        // duplicate turns, so only complete durable dialogue is deduplicated.
        if (!transient && checkAndDedupe(data.text)) break;
        meshBus.publish({
          taskId: parentTaskId,
          type: 'dialogue',
          payload: {
            operation: data.operation || 'stream',
            phase: data.phase || 'progress',
            agent: data.agent || agent,
            role: data.role || 'response',
            text: data.text || '',
            ...(transient ? { transient: true } : {}),
          },
        }, { persist: !transient });
        break;
      }

      case 'task-status': {
        const state = data.status?.state;
        if (state === 'working') {
          meshBus.publish({
            taskId: parentTaskId,
            type: 'dialogue',
            payload: {
              operation: 'stream', phase: 'status',
              agent, role: 'system',
              text: `${agent} processing...`,
            },
          });
        } else if (state === 'completed') {
          meshBus.publish({
            taskId: parentTaskId,
            type: 'dialogue',
            payload: {
              operation: 'stream', phase: 'complete',
              agent, role: 'system',
              text: `${agent} completed`,
            },
          });
        } else if (state === 'failed') {
          meshBus.publish({
            taskId: parentTaskId,
            type: 'dialogue',
            payload: {
              operation: 'stream', phase: 'error',
              agent, role: 'error',
              text: `${agent} failed: ${data.status?.message?.parts?.[0]?.text || 'unknown'}`,
            },
          });
        }
        break;
      }
    }
  }

  async function executeA2ACall(input, context) {
    const isSelfCall = input.agent === selfId;
    const peerUrl = isSelfCall ? selfUrl : peers[input.agent];
    if (!peerUrl) return `Unknown agent: ${input.agent}. Available: ${[...(selfUrl ? [selfId] : []), ...Object.keys(peers)].join(', ')}`;

    const enriched = enrichPromptIfContinuation(input.prompt, context, meshStore);
    if (enriched.enriched) {
      input = { ...input, prompt: enriched.prompt };
    }

    // Skip offline peers early if discovery is available (but not for self-calls)
    if (!isSelfCall && peerDiscovery) {
      const peerInfo = peerDiscovery.getPeer(input.agent);
      if (peerInfo && peerInfo.status === 'offline') {
        return `Error from ${input.agent}: peer is offline (last seen: ${peerInfo.lastSeen ? peerInfo.lastSeen.toISOString() : 'never'})`;
      }
    }

    const chain = normalizeMeshChain(context.meshChain);

    if ((context.depth ?? maxDepth) <= 0) return `Error: max mesh depth exceeded (chain: ${chain.join(' → ')})`;
    // Skip loop detection for self-calls (orchestrator legitimately calls itself as participant in debate/consensus)
    if (!isSelfCall && chain.includes(input.agent)) return `Error: loop detected — ${input.agent} already in chain: ${chain.join(' → ')}`;
    const currentSelfCallDepth = normalizePositiveInt(context.selfCallDepth, 0);
    if (isSelfCall && currentSelfCallDepth >= MAX_SELF_CALL_DEPTH) {
      return `Error: max self-call depth exceeded (${MAX_SELF_CALL_DEPTH})`;
    }
    const depth = Math.max(0, (context.depth ?? maxDepth) - 1);
    const timeoutMs = normalizeTimeoutMs(input.timeout_ms, DEFAULT_CALL_TIMEOUT_MS);

    const metadata = buildForwardedMetadata({
      maxDepth: depth,
      calledBy: selfId,
      parentTaskId: context.taskId,
      meshChain: appendSelfToMeshChain(chain, selfId),
      selfCallDepth: isSelfCall ? currentSelfCallDepth + 1 : currentSelfCallDepth,
      sessionId: context.sessionId,
    }, context, input, input.agent);

    const body = JSON.stringify({
      message: { role: 'user', parts: [{ type: 'text', text: input.prompt }] },
      sessionId: context.sessionId,
      metadata,
    });

    if (meshBus) {
      meshBus.publish({
        taskId: context.taskId, type: 'a2a_call',
        payload: { targetAgent: input.agent, prompt: input.prompt.slice(0, 5000) },
      });
    }

    const result = await streamTask(
      peerUrl, body, input.agent, context.taskId, timeoutMs, { signal: context.signal },
    );
    if (result.error) {
      if (result.partial && meshBus) {
        meshBus.publish({
          taskId: context.taskId,
          type: 'partial_output',
          payload: {
            operation: 'call',
            agent: input.agent,
            remoteTaskId: result.remoteTaskId || null,
            reason: result.error,
            text: String(result.partial).slice(-200_000),
          },
        });
      }
      return `Error from ${input.agent}: ${result.error}${result.remoteTaskId ? ` (remote task ${result.remoteTaskId})` : ''}`;
    }
    return result.response;
  }

  async function executeA2ABroadcast(input, context) {
    const chain = normalizeMeshChain(context.meshChain);
    if ((context.depth ?? maxDepth) <= 0) return `Error: max mesh depth exceeded (chain: ${chain.join(' → ')})`;
    const enriched = enrichPromptIfContinuation(input.prompt, context, meshStore);
    if (enriched.enriched) {
      input = { ...input, prompt: enriched.prompt };
    }
    const currentSelfCallDepth = normalizePositiveInt(context.selfCallDepth, 0);
    const timeoutMs = normalizeTimeoutMs(input.timeout_ms, DEFAULT_CALL_TIMEOUT_MS);
    const requestedAgents = Array.isArray(input.agents) && input.agents.length > 0
      ? input.agents
      : Object.keys(peers);
    const includeSelf = input.includeSelf === true;
    const agents = requestedAgents.filter(a => peers[a] && !chain.includes(a));
    const selfDepthAllowed = currentSelfCallDepth < MAX_SELF_CALL_DEPTH;
    const shouldRunSelf = includeSelf
      && selfDepthAllowed
      && Boolean(selfUrl)
      && !chain.includes(selfId)
      && (requestedAgents.includes(selfId) || !Array.isArray(input.agents) || input.agents.length === 0);
    if (agents.length === 0 && !shouldRunSelf) return 'Error: no agents available (all filtered by loop detection)';
    const depth = Math.max(0, (context.depth ?? maxDepth) - 1);

    const metadataBase = {
      maxDepth: depth, calledBy: selfId,
      parentTaskId: context.taskId,
      meshChain: appendSelfToMeshChain(chain, selfId),
      selfCallDepth: currentSelfCallDepth,
      sessionId: context.sessionId,
    };

    if (meshBus) {
      meshBus.publish({
        taskId: context.taskId, type: 'a2a_broadcast',
        payload: {
          targetAgents: shouldRunSelf ? [...agents, selfId] : agents,
          prompt: input.prompt.slice(0, 5000),
        },
      });
    }

    const bodyForAgent = (agent, metadataOverrides = {}) => JSON.stringify({
      message: { role: 'user', parts: [{ type: 'text', text: input.prompt }] },
      sessionId: context.sessionId,
      metadata: buildForwardedMetadata(
        { ...metadataBase, ...metadataOverrides },
        context,
        input,
        agent,
      ),
    });

    const broadcastTargets = shouldRunSelf
      ? [
          ...agents.map(agent => ({ agent, url: peers[agent], body: bodyForAgent(agent) })),
          { agent: selfId, url: selfUrl, body: bodyForAgent(selfId, { selfCallDepth: currentSelfCallDepth + 1 }) },
        ]
      : agents.map(agent => ({ agent, url: peers[agent], body: bodyForAgent(agent) }));
    const results = await Promise.all(broadcastTargets.map(async ({ agent, url, body: targetBody }) => {
      const result = await streamTask(
        url, targetBody || body, agent, context.taskId, timeoutMs, { signal: context.signal },
      );
      if (result.error && result.partial && meshBus) {
        meshBus.publish({
          taskId: context.taskId,
          type: 'partial_output',
          payload: {
            operation: 'broadcast',
            agent,
            remoteTaskId: result.remoteTaskId || null,
            reason: result.error,
            text: String(result.partial).slice(-200_000),
          },
        });
      }
      return {
        agent,
        response: result.response || null,
        error: result.error || null,
        remoteTaskId: result.remoteTaskId || null,
      };
    }));

    return results.map(r => `**${r.agent}**: ${r.response || r.error}`).join('\n\n---\n\n');
  }

  /**
   * Filter tools by depth. At depth 0, remove A2A tools to prevent recursion.
   * @param {number} depth
   * @param {Array} apiTools - Tool array in any provider format
   */
  function getToolsForDepth(depth, apiTools) {
    if (depth > 0) return apiTools;
    return apiTools.filter(t => {
      const name = t.name || t.function?.name;
      return !String(name || '').startsWith('a2a_');
    });
  }

  return { executeA2ACall, executeA2ABroadcast, getToolsForDepth };
}
