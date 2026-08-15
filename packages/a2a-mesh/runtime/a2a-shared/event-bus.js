/**
 * MeshEventBus — Peer-to-peer SSE event bus for A2A mesh
 *
 * Each server subscribes to peers' /mesh/events SSE endpoint.
 * Events propagate in real-time across the mesh network.
 * No external infrastructure required — pure HTTP SSE.
 */

import http from 'http';
import { EventEmitter } from 'events';

function formatError(err) {
  return err instanceof Error ? err.message : String(err);
}

export class MeshEventBus extends EventEmitter {
  constructor({ selfId, peers, store, authToken = '' }) {
    super();
    this.selfId = selfId;
    this.peers = peers;       // { codex: 'http://localhost:3141', ... }
    this.store = store;       // MeshStore instance
    this.authToken = authToken;
    this.sseClients = new Set();
    this.peerConnections = new Map();
    this._reconnectTimers = new Map();
  }

  /**
   * Publish an event — writes to SQLite + sends to all local SSE subscribers.
   * Only sends to non-peer SSE clients to prevent amplification loops.
   */
  publish(event) {
    const fullEvent = {
      ...event,
      server: this.selfId,
      timestamp: new Date().toISOString(),
    };

    // Write to SQLite
    if (this.store && event.taskId) {
      try {
        this.store.createEvent(event.taskId, event.type, this.selfId, event.payload || {});
      } catch (err) {
        console.warn('[mesh:event-bus] Failed to persist mesh event', {
          taskId: event.taskId,
          type: event.type,
          server: this.selfId,
          error: formatError(err),
        });
      }
    }

    // Emit locally (for in-process listeners)
    this.emit('event', fullEvent);

    // Push to non-peer SSE clients only (dashboards, external tools)
    // Peers receive events via their _connectToPeer subscription, not via publish()
    const payload = `event: mesh-event\ndata: ${JSON.stringify(fullEvent)}\n\n`;
    for (const client of this.sseClients) {
      if (client._isPeerConnection) continue;
      try {
        client.write(payload);
      } catch (err) {
        console.warn('[mesh:event-bus] Failed to write event payload to SSE client', {
          server: this.selfId,
          eventType: fullEvent.type,
          isPeerConnection: !!client._isPeerConnection,
          error: formatError(err),
        });
        this.sseClients.delete(client);
      }
    }
  }

  /**
   * HTTP handler for GET /mesh/events — SSE stream for external subscribers.
   */
  handleSSE(req, res) {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    });

    res.write(`: connected to ${this.selfId}\n\n`);
    // Mark peer connections to prevent event amplification loops
    const url = new URL(req.url, 'http://localhost');
    res._isPeerConnection = url.searchParams.get('peer') === 'true';
    this.sseClients.add(res);

    // Heartbeat every 30s to keep connection alive
    const heartbeat = setInterval(() => {
      try { res.write(': heartbeat\n\n'); } catch { clearInterval(heartbeat); }
    }, 30000);

    req.on('close', () => {
      this.sseClients.delete(res);
      clearInterval(heartbeat);
    });
  }

  /**
   * Connect to all peers' /mesh/events SSE endpoints.
   * Auto-reconnects on disconnect with 5s delay.
   */
  connectToPeers() {
    for (const [peerId, peerUrl] of Object.entries(this.peers)) {
      this._connectToPeer(peerId, peerUrl);
    }
  }

  _connectToPeer(peerId, peerUrl) {
    try {
      const url = new URL('/mesh/events?peer=true', peerUrl);

      const req = http.get(url, {
        headers: this.authToken
          ? { Authorization: `Bearer ${this.authToken}`, 'A2A-Token': this.authToken }
          : {},
      }, (res) => {
        if (res.statusCode !== 200) {
          console.warn('[mesh:event-bus] Peer SSE returned non-200 status', {
            peerId,
            peerUrl,
            statusCode: res.statusCode,
          });
          res.resume();
          this._scheduleReconnect(peerId, peerUrl);
          return;
        }

        console.log(`[mesh] Connected to peer ${peerId} at ${peerUrl}`);
        this.peerConnections.set(peerId, req);

        let buffer = '';
        res.on('data', (chunk) => {
          buffer += chunk.toString();
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event = JSON.parse(line.slice(6));
                // Re-emit as peer event (don't re-publish to avoid loops)
                this.emit('peer-event', { peerId, ...event });

                // Forward ONLY to non-peer SSE clients (dashboards, external)
                // Skip peer connections to prevent event amplification loops
                const payload = `event: peer-event\ndata: ${JSON.stringify({ peerId, ...event })}\n\n`;
                for (const client of this.sseClients) {
                  if (client._isPeerConnection) continue; // skip peers
                  try {
                    client.write(payload);
                  } catch (err) {
                    console.warn('[mesh:event-bus] Failed to forward peer event to SSE client', {
                      peerId,
                      server: this.selfId,
                      isPeerConnection: !!client._isPeerConnection,
                      error: formatError(err),
                    });
                    this.sseClients.delete(client);
                  }
                }
              } catch (err) {
                console.warn('[mesh:event-bus] Failed to parse peer SSE data payload', {
                  peerId,
                  peerUrl,
                  linePreview: line.slice(0, 200),
                  error: formatError(err),
                });
              }
            }
          }
        });

        res.on('end', () => {
          this.peerConnections.delete(peerId);
          this._scheduleReconnect(peerId, peerUrl);
        });
      });

      req.on('error', (err) => {
        console.warn('[mesh:event-bus] Peer SSE connection error', {
          peerId,
          peerUrl,
          error: formatError(err),
        });
        this._scheduleReconnect(peerId, peerUrl);
      });

      req.setTimeout(0); // no timeout for long-lived SSE
    } catch (err) {
      console.warn('[mesh:event-bus] Failed to initialize peer SSE connection', {
        peerId,
        peerUrl,
        error: formatError(err),
      });
      this._scheduleReconnect(peerId, peerUrl);
    }
  }

  _scheduleReconnect(peerId, peerUrl) {
    if (this._reconnectTimers.has(peerId)) return;
    const timer = setTimeout(() => {
      this._reconnectTimers.delete(peerId);
      this._connectToPeer(peerId, peerUrl);
    }, 5000);
    this._reconnectTimers.set(peerId, timer);
  }

  /**
   * Get connection status for all peers.
   */
  getStatus() {
    const status = {};
    for (const [peerId] of Object.entries(this.peers)) {
      status[peerId] = this.peerConnections.has(peerId) ? 'connected' : 'disconnected';
    }
    return {
      selfId: this.selfId,
      sseClients: this.sseClients.size,
      peers: status,
    };
  }

  /**
   * Gracefully disconnect all peers and clients.
   */
  disconnect() {
    for (const [, req] of this.peerConnections) {
      // Benign cleanup: socket may already be closed.
      try {
        req.destroy();
      } catch (err) {
        if (process.env.A2A_DEBUG === 'true') {
          console.warn('[mesh] Failed to destroy peer request during disconnect', {
            selfId: this.selfId,
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    }
    for (const [, timer] of this._reconnectTimers) {
      clearTimeout(timer);
    }
    for (const client of this.sseClients) {
      // Benign cleanup: client stream may already be closed.
      try {
        client.end();
      } catch (err) {
        if (process.env.A2A_DEBUG === 'true') {
          console.warn('[mesh] Failed to end SSE client during disconnect', {
            selfId: this.selfId,
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    }
    this.peerConnections.clear();
    this._reconnectTimers.clear();
    this.sseClients.clear();
  }
}
