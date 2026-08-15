// ============================================
// Peer Registry — central peer/self URL resolution
// ============================================

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { DEFAULT_PORTS } from './agent-catalog.js';

function parseJsonSafe(raw) {
  if (!raw || typeof raw !== 'string') return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function normalizeUrl(url) {
  if (typeof url !== 'string') return '';
  return url.trim().replace(/\/+$/, '');
}

function inferPeerUrl(agentId) {
  const upper = String(agentId || '').toUpperCase();
  const explicitUrl = process.env[`A2A_${upper}_URL`];
  if (explicitUrl) return normalizeUrl(explicitUrl);

  const defaultPort = DEFAULT_PORTS[agentId];
  const explicitPort = process.env[`A2A_${upper}_PORT`];
  const port = explicitPort || defaultPort;
  if (!port) return '';
  return `http://localhost:${port}`;
}

/**
 * Load peer registry from ENV/JSON file plus local defaults.
 * Priority order:
 *   1) A2A_PEERS_JSON
 *   2) A2A_PEERS_FILE (default ~/.a2a/peers.json)
 *   3) per-agent URL/PORT env vars
 */
export function loadPeerRegistry({ selfId = '', includeSelf = false } = {}) {
  let peers = {};

  const fromEnv = parseJsonSafe(process.env.A2A_PEERS_JSON);
  if (fromEnv) peers = { ...peers, ...fromEnv };

  const filePath = process.env.A2A_PEERS_FILE || path.join(os.homedir(), '.a2a', 'peers.json');
  if (fs.existsSync(filePath)) {
    const fromFile = parseJsonSafe(fs.readFileSync(filePath, 'utf8'));
    if (fromFile) peers = { ...peers, ...fromFile };
  }

  for (const agentId of Object.keys(DEFAULT_PORTS)) {
    if (!peers[agentId]) {
      const inferred = inferPeerUrl(agentId);
      if (inferred) peers[agentId] = inferred;
    }
  }

  const normalized = {};
  for (const [agentId, url] of Object.entries(peers)) {
    const cleanUrl = normalizeUrl(url);
    if (cleanUrl) normalized[agentId] = cleanUrl;
  }

  if (!includeSelf && selfId) delete normalized[selfId];
  return normalized;
}

// --- Agent card fetch with caching ---

let _cardCache = null;     // { data: { agentId: { url, agentCard } }, expiry: number }
const CARD_CACHE_TTL = 60_000; // 60 seconds

/**
 * Fetch agent cards from all known peers.
 * Returns { agentId: { url, agentCard } } map.
 * Results are cached for 60 seconds; failed fetches are silently skipped.
 *
 * @param {Object} [options]
 * @param {string} [options.selfId] - Exclude this agent from results
 * @param {Object} [options.peers]  - Pre-loaded peer map; if omitted, loads from registry
 * @param {number} [options.timeoutMs=3000] - Per-fetch timeout in ms
 * @param {boolean} [options.forceRefresh=false] - Bypass cache
 * @returns {Promise<Object>} { agentId: { url, agentCard } }
 */
export async function fetchAgentCards({ selfId = '', peers: peersArg, timeoutMs = 3000, forceRefresh = false } = {}) {
  // Return cached result if still valid
  if (!forceRefresh && _cardCache && Date.now() < _cardCache.expiry) {
    return _cardCache.data;
  }

  const peers = peersArg || loadPeerRegistry({ selfId });
  const entries = Object.entries(peers);
  const result = {};

  const fetches = entries.map(async ([agentId, url]) => {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const res = await fetch(`${url}/.well-known/agent.json`, {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      clearTimeout(timer);
      if (!res.ok) return; // skip non-200
      const agentCard = await res.json();
      result[agentId] = { url, agentCard };
    } catch {
      // Peer unreachable or timed out — skip silently
    }
  });

  await Promise.all(fetches);

  _cardCache = { data: result, expiry: Date.now() + CARD_CACHE_TTL };
  return result;
}

/**
 * Clear the agent card cache (useful in tests).
 */
export function clearAgentCardCache() {
  _cardCache = null;
}

/**
 * Resolve this server's own base URL.
 */
export function resolveSelfUrl({ selfId = '', peers } = {}) {
  const explicit = normalizeUrl(process.env.A2A_SELF_URL);
  if (explicit) return explicit;

  if (process.env.A2A_PORT) return `http://localhost:${process.env.A2A_PORT}`;

  if (peers && selfId && peers[selfId]) return normalizeUrl(peers[selfId]);

  const registry = loadPeerRegistry({ includeSelf: true });
  if (selfId && registry[selfId]) return registry[selfId];

  const inferred = inferPeerUrl(selfId);
  return inferred || '';
}

// ============================================
// PeerDiscovery — dynamic health-based peer discovery
// ============================================

const HEALTH_CHECK_TIMEOUT_MS = 3000;
const AGENT_CARD_CACHE_TTL_MS = 60000;
const HEALTH_CHECK_INTERVAL_MS = 30000;

export class PeerDiscovery {
  /**
   * @param {Object} initialPeers - { agentId: url } from loadPeerRegistry()
   */
  constructor(initialPeers) {
    this._peers = {};
    for (const [agentId, url] of Object.entries(initialPeers || {})) {
      this._peers[agentId] = {
        url,
        status: 'unknown',
        lastSeen: null,
        agentCard: null,
        agentCardFetchedAt: null,
        protocolVersion: null,
      };
    }
    this._intervalId = null;
  }

  /**
   * Begin periodic health checks.
   */
  async start() {
    await this.checkAllHealth();
    this._intervalId = setInterval(() => {
      this.checkAllHealth().catch(() => {});
    }, HEALTH_CHECK_INTERVAL_MS);
    // Unref so the interval doesn't keep the process alive
    if (this._intervalId && typeof this._intervalId.unref === 'function') {
      this._intervalId.unref();
    }
  }

  /**
   * Stop periodic health checks.
   */
  stop() {
    if (this._intervalId !== null) {
      clearInterval(this._intervalId);
      this._intervalId = null;
    }
  }

  /**
   * Check health of a single peer.
   * @param {string} agentId
   * @returns {Promise<boolean>} true if peer is online
   */
  async checkHealth(agentId) {
    const peer = this._peers[agentId];
    if (!peer) return false;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT_MS);

    try {
      const resp = await fetch(`${peer.url}/health`, {
        method: 'GET',
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (resp.ok) {
        peer.status = 'online';
        peer.lastSeen = new Date();
        try {
          const data = await resp.json();
          if (data.protocolVersion) {
            peer.protocolVersion = data.protocolVersion;
          }
        } catch {
          // JSON parse error — health endpoint is still reachable
        }
        // Fetch agent card if not cached or TTL expired
        const cardExpired = !peer.agentCardFetchedAt ||
          (Date.now() - peer.agentCardFetchedAt.getTime()) > AGENT_CARD_CACHE_TTL_MS;
        if (!peer.agentCard || cardExpired) {
          await this.fetchAgentCard(agentId);
        }
        return true;
      }
      peer.status = 'offline';
      return false;
    } catch {
      clearTimeout(timeout);
      peer.status = 'offline';
      return false;
    }
  }

  /**
   * Check health of all known peers.
   * @returns {Promise<Object>} { agentId: boolean }
   */
  async checkAllHealth() {
    const results = {};
    const agentIds = Object.keys(this._peers);
    await Promise.all(agentIds.map(async (agentId) => {
      results[agentId] = await this.checkHealth(agentId);
    }));
    return results;
  }

  /**
   * Get peer info with status.
   * @param {string} agentId
   * @returns {Object|null}
   */
  getPeer(agentId) {
    const peer = this._peers[agentId];
    if (!peer) return null;
    return {
      url: peer.url,
      status: peer.status,
      lastSeen: peer.lastSeen,
      agentCard: peer.agentCard,
      protocolVersion: peer.protocolVersion,
    };
  }

  /**
   * Get only online peers.
   * @returns {Object} { agentId: peerInfo }
   */
  getOnlinePeers() {
    const result = {};
    for (const [agentId, peer] of Object.entries(this._peers)) {
      if (peer.status === 'online') {
        result[agentId] = {
          url: peer.url,
          status: peer.status,
          lastSeen: peer.lastSeen,
          agentCard: peer.agentCard,
          protocolVersion: peer.protocolVersion,
        };
      }
    }
    return result;
  }

  /**
   * Get all peers with status.
   * @returns {Object} { agentId: peerInfo }
   */
  getAllPeers() {
    const result = {};
    for (const [agentId, peer] of Object.entries(this._peers)) {
      result[agentId] = {
        url: peer.url,
        status: peer.status,
        lastSeen: peer.lastSeen,
        agentCard: peer.agentCard,
        protocolVersion: peer.protocolVersion,
      };
    }
    return result;
  }

  /**
   * Fetch and cache agent card for a peer.
   * @param {string} agentId
   * @returns {Promise<Object|null>} the agent card, or null on failure
   */
  async fetchAgentCard(agentId) {
    const peer = this._peers[agentId];
    if (!peer) return null;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT_MS);

    try {
      const resp = await fetch(`${peer.url}/.well-known/agent.json`, {
        method: 'GET',
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (resp.ok) {
        const card = await resp.json();
        peer.agentCard = card;
        peer.agentCardFetchedAt = new Date();
        if (card.protocolVersion) {
          peer.protocolVersion = card.protocolVersion;
        }
        return card;
      }
      return null;
    } catch {
      clearTimeout(timeout);
      return null;
    }
  }

  /**
   * Check if a specific peer is currently online.
   * @param {string} agentId
   * @returns {boolean}
   */
  isOnline(agentId) {
    const peer = this._peers[agentId];
    return peer ? peer.status === 'online' : false;
  }
}
