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

  _markDelivered(client, key) {
    if (!key) return true;
    if (client._deliveredEventKeys.has(key)) return false;
    client._deliveredEventKeys.add(key);
    client._deliveredEventOrder.push(key);
    while (client._deliveredEventOrder.length > 10_000) {
      client._deliveredEventKeys.delete(client._deliveredEventOrder.shift());
    }
    return true;
  }

  /**
   * Publish an event — writes to SQLite + sends it to dashboards and peer
   * subscribers. A receiving peer only forwards to its own dashboards; it
   * never calls publish(), which is the actual loop-prevention boundary.
   */
  publish(event, { persist = true } = {}) {
    const fullEvent = {
      ...event,
      server: this.selfId,
      timestamp: new Date().toISOString(),
    };

    // Write to SQLite
    let eventId = null;
    let dropped = false;
    if (persist && this.store && event.taskId) {
      try {
        if (typeof this.store.createEventDetailed === 'function') {
          const persisted = this.store.createEventDetailed(
            event.taskId, event.type, this.selfId, event.payload || {},
          );
          eventId = persisted.id;
          dropped = persisted.dropped;
          if (persisted.gapPayload) {
            fullEvent.type = 'mesh_gap';
            fullEvent.payload = persisted.gapPayload;
          }
        } else {
          eventId = this.store.createEvent(event.taskId, event.type, this.selfId, event.payload || {});
        }
      } catch (err) {
        console.warn('[mesh:event-bus] Failed to persist mesh event', {
          taskId: event.taskId,
          type: event.type,
          server: this.selfId,
          error: formatError(err),
        });
      }
    }
    if (dropped && !eventId) return null;
    if (eventId) fullEvent.eventId = eventId;

    // Emit locally (for in-process listeners)
    this.emit('event', fullEvent);

    // Push to dashboards, external tools and peer subscribers. Peer receivers
    // do not re-publish, so an event traverses at most one peer hop.
    const payload = `${eventId ? `id: ${eventId}\n` : ''}event: mesh-event\ndata: ${JSON.stringify(fullEvent)}\n\n`;
    for (const client of this.sseClients) {
      try {
        const dedupeKey = eventId ? `${this.selfId}:${eventId}` : null;
        if (client._replaying) client._pendingMeshEvents.push({ payload, dedupeKey });
        else if (this._markDelivered(client, dedupeKey)) client.write(payload);
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

    // Mark peer connections to prevent event amplification loops
    const url = new URL(req.url, 'http://localhost');
    res._isPeerConnection = url.searchParams.get('peer') === 'true';
    res._replaying = true;
    res._pendingMeshEvents = [];
    res._replayedEventKeys = new Set();
    res._deliveredEventKeys = new Set();
    res._deliveredEventOrder = [];
    this.sseClients.add(res);

    // Dashboard reconnects can request a durable replay by SQLite event id.
    // Peer links intentionally skip replay to avoid propagating old events.
    if (!res._isPeerConnection && this.store) {
      const headerId = Number.parseInt(String(req.headers['last-event-id'] || ''), 10);
      const queryId = Number.parseInt(String(url.searchParams.get('after') || ''), 10);
      const afterId = Number.isFinite(headerId) ? headerId : (Number.isFinite(queryId) ? queryId : 0);
      if (afterId > 0) {
        try {
          const configuredLimit = Number.parseInt(process.env.MESH_SSE_REPLAY_MAX || '1000', 10);
          const replayLimit = Number.isFinite(configuredLimit)
            ? Math.max(1, configuredLimit)
            : 1_000;
          const pageSize = Math.min(1000, replayLimit);
          let cursor = afterId;
          let replayedCount = 0;
          while (replayedCount < replayLimit) {
            const limit = Math.min(pageSize, replayLimit - replayedCount);
            const missed = this.store.getTimeline({ afterId: cursor, order: 'asc', limit });
            for (const item of missed) {
              const replay = {
                taskId: item.task_id,
                type: item.event_type,
                payload: item.payload,
                server: item.server,
                timestamp: item.created_at,
                eventId: item.id,
                replayed: true,
              };
              res.write(`id: ${item.id}\nevent: mesh-event\ndata: ${JSON.stringify(replay)}\n\n`);
              const replayKey = `${item.server}:${item.id}`;
              res._replayedEventKeys.add(replayKey);
              this._markDelivered(res, replayKey);
              cursor = item.id;
              replayedCount += 1;
            }
            if (missed.length < limit) break;
          }
          const more = this.store.getTimeline({ afterId: cursor, order: 'asc', limit: 1 });
          if (more.length > 0) {
            res.write(`event: mesh-gap\ndata: ${JSON.stringify({
              fromEventId: afterId,
              nextAfterId: cursor,
              replayLimit,
              message: 'Replay limit reached; request the remaining timeline pages.',
            })}\n\n`);
          }
        } catch (err) {
          console.warn('[mesh:event-bus] Failed to replay missed events', { error: formatError(err), afterId });
        }
      }
    }
    res._replaying = false;
    for (const pending of res._pendingMeshEvents) {
      if (!pending.dedupeKey || (
        !res._replayedEventKeys.has(pending.dedupeKey)
        && this._markDelivered(res, pending.dedupeKey)
      )) {
        res.write(pending.payload);
      }
    }
    res._pendingMeshEvents.length = 0;
    res._replayedEventKeys.clear();
    res.write(`: connected to ${this.selfId}\n\n`);

    // Heartbeat every 30s to keep connection alive
    const heartbeat = setInterval(() => {
      try { res.write(': heartbeat\n\n'); } catch { clearInterval(heartbeat); }
    }, 30000);

    res.on('close', () => {
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
                // A peer's numeric event id is namespaced and must not become
                // EventSource's global Last-Event-ID cursor for this server.
                const payload = `event: peer-event\ndata: ${JSON.stringify({ peerId, ...event })}\n\n`;
                for (const client of this.sseClients) {
                  if (client._isPeerConnection) continue; // skip peers
                  try {
                    const dedupeKey = event.eventId ? `${event.server || peerId}:${event.eventId}` : null;
                    if (client._replaying) client._pendingMeshEvents.push({ payload, dedupeKey });
                    else if (this._markDelivered(client, dedupeKey)) client.write(payload);
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
