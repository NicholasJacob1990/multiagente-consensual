import { A2A_PROTOCOL_VERSION, A2A_VERSION_HEADER } from './protocol.js';

function headers(authToken, json = false) {
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION,
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  };
}

function timeoutSignal(timeoutMs) {
  return AbortSignal.timeout(Math.max(1, timeoutMs));
}

function boundedSignal(timeoutMs, signal) {
  const timeout = timeoutSignal(timeoutMs);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export async function fetchRemoteTask(peerUrl, taskId, {
  authToken = '',
  timeoutMs = 10_000,
  signal,
} = {}) {
  const response = await fetch(`${peerUrl}/tasks/${encodeURIComponent(taskId)}`, {
    headers: headers(authToken),
    signal: boundedSignal(timeoutMs, signal),
  });
  if (!response.ok) throw new Error(`task recovery HTTP ${response.status}`);
  const payload = await response.json();
  return payload.result || payload;
}

export async function cancelRemoteTask(peerUrl, taskId, {
  authToken = '',
  timeoutMs = 10_000,
} = {}) {
  if (!peerUrl || !taskId) return { canceled: false, reason: 'remote task is unknown' };
  try {
    const response = await fetch(`${peerUrl}/tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: 'POST',
      headers: headers(authToken, true),
      body: '{}',
      signal: timeoutSignal(timeoutMs),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = payload?.error?.message || payload?.error || `HTTP ${response.status}`;
      return { canceled: false, reason: String(message), task: payload?.result };
    }
    return { canceled: true, task: payload.result || payload };
  } catch (error) {
    return { canceled: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

export function waitForRemotePoll(ms, signal) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', finish);
      resolve();
    };
    const timer = setTimeout(finish, Math.max(0, ms));
    if (signal) {
      if (signal.aborted) finish();
      else signal.addEventListener('abort', finish, { once: true });
    }
  });
}

export async function recoverRemoteTask(peerUrl, taskId, {
  authToken = '',
  deadline,
  signal,
  pollMs = 2_000,
  onPollError,
} = {}) {
  while (Date.now() < deadline) {
    if (signal?.aborted) {
      return { error: 'Task canceled by caller', remoteTaskId: taskId, retryable: false };
    }
    try {
      const remaining = Math.max(1, deadline - Date.now());
      const task = await fetchRemoteTask(peerUrl, taskId, {
        authToken,
        timeoutMs: Math.min(10_000, remaining),
        signal,
      });
      const state = task.status?.state || task.state;
      const text = task.status?.message?.parts?.map((part) => part.text).filter(Boolean).join('\n')
        || task.outputText || task.error || '';
      if (state === 'completed') {
        return { response: text || 'No response', remoteTaskId: taskId, retryable: false };
      }
      if (['failed', 'canceled', 'rejected'].includes(state)) {
        return { error: text || `Remote task ${state}`, remoteTaskId: taskId, retryable: false };
      }
    } catch (error) {
      if (signal?.aborted) {
        return { error: 'Task canceled by caller', remoteTaskId: taskId, retryable: false };
      }
      onPollError?.(error);
    }
    await waitForRemotePoll(Math.min(pollMs, Math.max(0, deadline - Date.now())), signal);
  }
  return {
    error: 'Remote task is still running after the call timeout',
    remoteTaskId: taskId,
    retryable: false,
  };
}
