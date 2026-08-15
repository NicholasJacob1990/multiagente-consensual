/**
 * MeshStore — Shared SQLite store for A2A mesh network
 *
 * Uses better-sqlite3 for synchronous, WAL-mode access.
 * All 3 servers (claude, codex, gemini) share the same mesh.db.
 */

import { createRequire } from 'module';
import path from 'path';
import os from 'os';
import fs from 'fs';
import { randomUUID } from 'crypto';

const require = createRequire(import.meta.url);
const Database = require('better-sqlite3');

const DEFAULT_DB_PATH = path.join(os.homedir(), '.a2a', 'mesh.db');

export class MeshStore {
  constructor(dbPath = DEFAULT_DB_PATH) {
    const dir = path.dirname(dbPath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('busy_timeout = 5000');
    this._migrate();

    // Loop-protection: cap events persisted per task to avoid the runaway
    // duplication bug observed 2026-04-30 (one task accumulated 488+ identical
    // dialogue events; over a couple of weeks that pattern produced a 27GB
    // mesh.db). Exact root cause not yet identified — this is defensive.
    this._eventCounts = new Map();
    this._loopReported = new Set();
    this.MAX_EVENTS_PER_TASK = parseInt(process.env.MESH_MAX_EVENTS_PER_TASK || '2000', 10);
  }

  // Schema version pinned in SQLite's PRAGMA user_version. Bump when adding
  // a column/index that older databases lack — write a migration step that
  // upgrades the schema in-place. Without this gating, `CREATE TABLE IF NOT
  // EXISTS` silently no-ops on stale schemas and queries fail at runtime.
  static SCHEMA_VERSION = 2;

  _runMigrationStep(version, sql) {
    // BEGIN IMMEDIATE acquires the write lock up-front so a parallel server
    // instance (e.g. all 3 mesh agents starting via launchd) doesn't race past
    // the version check and double-apply. better-sqlite3 honors busy_timeout
    // (5s, set in constructor) so this waits patiently for any in-flight
    // migration to finish.
    this.db.exec('BEGIN IMMEDIATE');
    try {
      // Re-check inside the lock — another process may have completed this
      // migration between our outer check and acquiring the write lock.
      const inLock = this.db.pragma('user_version', { simple: true });
      if (inLock >= version) {
        this.db.exec('ROLLBACK');
        return;
      }
      this.db.exec(sql);
      this.db.pragma(`user_version = ${version}`);
      this.db.exec('COMMIT');
      if (version > 1) console.log(`[mesh-store] Applied schema migration → v${version}`);
    } catch (err) {
      try { this.db.exec('ROLLBACK'); } catch { /* lock already released */ }
      throw new Error(`mesh-store migration → v${version} failed: ${err.message}`);
    }
  }

  _migrate() {
    const current = this.db.pragma('user_version', { simple: true });
    if (current > MeshStore.SCHEMA_VERSION) {
      throw new Error(`mesh-store schema is at v${current} but this build expects ≤v${MeshStore.SCHEMA_VERSION}. Refusing to start with a newer DB to avoid corruption.`);
    }
    if (current === MeshStore.SCHEMA_VERSION) return; // up to date

    // v0 → v1: initial schema.
    if (current < 1) this._runMigrationStep(1, `
      CREATE TABLE IF NOT EXISTS tasks (
        id              TEXT PRIMARY KEY,
        session_id      TEXT,
        origin_server   TEXT NOT NULL,
        parent_task_id  TEXT,
        called_by       TEXT,
        mesh_chain      TEXT DEFAULT '[]',
        depth           INTEGER DEFAULT 7,
        state           TEXT NOT NULL DEFAULT 'submitted',
        input_text      TEXT,
        output_text     TEXT,
        error           TEXT,
        artifacts       TEXT DEFAULT '[]',
        metadata        TEXT DEFAULT '{}',
        history         TEXT DEFAULT '[]',
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS task_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     TEXT NOT NULL,
        event_type  TEXT NOT NULL,
        server      TEXT NOT NULL,
        payload     TEXT DEFAULT '{}',
        created_at  TEXT DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS mesh_threads (
        id               TEXT PRIMARY KEY,
        title            TEXT,
        status           TEXT NOT NULL DEFAULT 'active',
        current_mode     TEXT,
        current_task_id  TEXT,
        summary          TEXT,
        metadata         TEXT DEFAULT '{}',
        created_at       TEXT DEFAULT (datetime('now')),
        updated_at       TEXT DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS mesh_context_snapshots (
        id          TEXT PRIMARY KEY,
        thread_id   TEXT NOT NULL,
        task_id     TEXT,
        mode        TEXT NOT NULL,
        title       TEXT,
        summary     TEXT NOT NULL,
        decisions   TEXT DEFAULT '[]',
        next_steps  TEXT DEFAULT '[]',
        errors      TEXT DEFAULT '[]',
        artifacts   TEXT DEFAULT '[]',
        metadata    TEXT DEFAULT '{}',
        created_at  TEXT DEFAULT (datetime('now'))
      );

      CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
      CREATE INDEX IF NOT EXISTS idx_tasks_parent_created_id ON tasks(parent_task_id, created_at, id);
      CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
      CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
      CREATE INDEX IF NOT EXISTS idx_tasks_origin ON tasks(origin_server);
      CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id);
      CREATE INDEX IF NOT EXISTS idx_events_type ON task_events(event_type);
      CREATE INDEX IF NOT EXISTS idx_events_created_id ON task_events(created_at DESC, id DESC);
      CREATE INDEX IF NOT EXISTS idx_threads_updated ON mesh_threads(updated_at DESC);
      CREATE INDEX IF NOT EXISTS idx_context_thread_created ON mesh_context_snapshots(thread_id, created_at DESC);
      CREATE INDEX IF NOT EXISTS idx_context_mode_created ON mesh_context_snapshots(mode, created_at DESC);
    `);

    // v1 → v2: provider-agnostic runtime session contract for tasks.
    if (current < 2) this._runMigrationStep(2, `
      ALTER TABLE tasks ADD COLUMN provider_session_id TEXT;
      ALTER TABLE tasks ADD COLUMN provider_session_key TEXT;
      ALTER TABLE tasks ADD COLUMN runtime TEXT;

      CREATE INDEX IF NOT EXISTS idx_tasks_provider_session_key ON tasks(provider_session_key);
      CREATE INDEX IF NOT EXISTS idx_tasks_runtime ON tasks(runtime);
    `);
  }

  // ---- Task CRUD ----

  createTask({
    id,
    sessionId,
    originServer,
    parentTaskId,
    calledBy,
    meshChain,
    depth,
    inputText,
    metadata,
    providerSessionId,
    providerSessionKey,
    runtime,
  }) {
    this.db.prepare(`
      INSERT INTO tasks (
        id, session_id, origin_server, parent_task_id, called_by, mesh_chain,
        depth, state, input_text, metadata, provider_session_id,
        provider_session_key, runtime
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?, ?, ?, ?)
    `).run(
      id, sessionId || null, originServer,
      parentTaskId || null, calledBy || null,
      JSON.stringify(meshChain || []),
      depth ?? 3,
      inputText || null,
      JSON.stringify(metadata || {}),
      providerSessionId || null,
      providerSessionKey || null,
      runtime || null
    );

    this.createEvent(id, 'created', originServer, { inputText: (inputText || '').slice(0, 5000) });
    return this.getTask(id);
  }

  updateTask(id, updates) {
    const sets = ["updated_at = datetime('now')"];
    const params = [];

    if (updates.state) { sets.push('state = ?'); params.push(updates.state); }
    if (updates.outputText !== undefined) { sets.push('output_text = ?'); params.push(updates.outputText); }
    if (updates.error !== undefined) { sets.push('error = ?'); params.push(updates.error); }
    if (updates.artifacts !== undefined) { sets.push('artifacts = ?'); params.push(JSON.stringify(updates.artifacts)); }
    if (updates.history !== undefined) { sets.push('history = ?'); params.push(JSON.stringify(updates.history)); }
    if (updates.providerSessionId !== undefined) { sets.push('provider_session_id = ?'); params.push(updates.providerSessionId); }
    if (updates.providerSessionKey !== undefined) { sets.push('provider_session_key = ?'); params.push(updates.providerSessionKey); }
    if (updates.runtime !== undefined) { sets.push('runtime = ?'); params.push(updates.runtime); }

    if (sets.length <= 1) return this.getTask(id); // nothing to update

    params.push(id);
    this.db.prepare(`UPDATE tasks SET ${sets.join(', ')} WHERE id = ?`).run(...params);
    return this.getTask(id);
  }

  getTask(id) {
    const row = this.db.prepare('SELECT * FROM tasks WHERE id = ?').get(id);
    if (!row) return null;
    return this._deserializeTask(row);
  }

  listTasks(filter = {}) {
    let sql = 'SELECT * FROM tasks';
    const conditions = [];
    const params = [];

    if (filter.state) { conditions.push('state = ?'); params.push(filter.state); }
    if (filter.originServer) { conditions.push('origin_server = ?'); params.push(filter.originServer); }
    if (filter.sessionId) { conditions.push('session_id = ?'); params.push(filter.sessionId); }
    if (filter.parentTaskId) { conditions.push('parent_task_id = ?'); params.push(filter.parentTaskId); }
    if (filter.providerSessionKey) { conditions.push('provider_session_key = ?'); params.push(filter.providerSessionKey); }
    if (filter.runtime) { conditions.push('runtime = ?'); params.push(filter.runtime); }

    if (conditions.length > 0) sql += ' WHERE ' + conditions.join(' AND ');
    sql += ' ORDER BY created_at DESC';
    if (filter.limit) { sql += ' LIMIT ?'; params.push(filter.limit); }

    return this.db.prepare(sql).all(...params).map(r => this._deserializeTask(r));
  }

  // ---- Mesh trace (recursive tree) ----

  getTrace(taskId) {
    const root = this.db.prepare(`
      WITH RECURSIVE parents AS (
        SELECT id, parent_task_id
        FROM tasks
        WHERE id = ?
        UNION ALL
        SELECT t.id, t.parent_task_id
        FROM tasks t
        JOIN parents p ON p.parent_task_id = t.id
      )
      SELECT id
      FROM parents
      WHERE parent_task_id IS NULL
      LIMIT 1
    `).get(taskId);
    if (!root?.id) return null;

    const rows = this.db.prepare(`
      WITH RECURSIVE tree AS (
        SELECT *
        FROM tasks
        WHERE id = ?
        UNION ALL
        SELECT c.*
        FROM tasks c
        JOIN tree p ON c.parent_task_id = p.id
      )
      SELECT *
      FROM tree
      ORDER BY created_at, id
    `).all(root.id);

    return this._buildTreeFromRows(rows, root.id);
  }

  _buildTreeFromRows(rows, rootId) {
    if (!Array.isArray(rows) || rows.length === 0) return null;

    const byId = new Map(rows.map(row => {
      const task = this._deserializeTask(row);
      return [task.id, { ...task, children: [] }];
    }));

    let rootNode = byId.get(rootId) || null;
    for (const node of byId.values()) {
      if (node.parentTaskId && byId.has(node.parentTaskId)) {
        byId.get(node.parentTaskId).children.push(node);
      } else if (!node.parentTaskId) {
        rootNode = rootNode || node;
      }
    }

    return rootNode;
  }

  // ---- Events ----

  createEvent(taskId, eventType, server, payload = {}) {
    // Loop guard: drop writes when a task crosses MAX_EVENTS_PER_TASK.
    // Always allow terminal-state events through so completion is recorded.
    const current = (this._eventCounts.get(taskId) || 0) + 1;
    this._eventCounts.set(taskId, current);

    const isTerminal = eventType === 'completed' || eventType === 'failed' || eventType === 'canceled';
    if (current > this.MAX_EVENTS_PER_TASK && !isTerminal) {
      if (!this._loopReported.has(taskId)) {
        this._loopReported.add(taskId);
        console.warn('[mesh-store] LOOP GUARD: task exceeded event limit, dropping further non-terminal events', {
          taskId, server, eventType, count: current, limit: this.MAX_EVENTS_PER_TASK,
        });
      }
      return;
    }

    this.db.prepare(
      'INSERT INTO task_events (task_id, event_type, server, payload) VALUES (?, ?, ?, ?)'
    ).run(taskId, eventType, server, JSON.stringify(payload));

    if (isTerminal) {
      // Terminal — release counter memory (don't grow unbounded)
      this._eventCounts.delete(taskId);
      this._loopReported.delete(taskId);
    }
  }

  getEvents(taskId) {
    return this.db.prepare(
      'SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at, id'
    ).all(taskId).map(r => ({ ...r, payload: JSON.parse(r.payload || '{}') }));
  }

  getTimeline(options = {}) {
    let sql = 'SELECT * FROM task_events';
    const conditions = [];
    const params = [];

    if (options.taskId) { conditions.push('task_id = ?'); params.push(options.taskId); }
    if (options.server) { conditions.push('server = ?'); params.push(options.server); }
    if (options.eventType) { conditions.push('event_type = ?'); params.push(options.eventType); }
    if (options.since) { conditions.push('created_at >= ?'); params.push(options.since); }

    if (conditions.length > 0) sql += ' WHERE ' + conditions.join(' AND ');
    sql += ' ORDER BY created_at DESC, id DESC';
    sql += ` LIMIT ${parseInt(options.limit) || 100}`;

    return this.db.prepare(sql).all(...params).map(r => ({ ...r, payload: JSON.parse(r.payload || '{}') }));
  }

  // ---- Stats / Dashboard ----

  getStats() {
    return {
      totalTasks: this.db.prepare('SELECT COUNT(*) as n FROM tasks').get().n,
      activeTasks: this.db.prepare("SELECT COUNT(*) as n FROM tasks WHERE state = 'working'").get().n,
      completedTasks: this.db.prepare("SELECT COUNT(*) as n FROM tasks WHERE state = 'completed'").get().n,
      failedTasks: this.db.prepare("SELECT COUNT(*) as n FROM tasks WHERE state = 'failed'").get().n,
      byServer: this.db.prepare(`
        SELECT origin_server,
               COUNT(*) as total,
               SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
               SUM(CASE WHEN state = 'working' THEN 1 ELSE 0 END) as active
        FROM tasks GROUP BY origin_server
      `).all(),
      meshCalls: this.db.prepare("SELECT COUNT(*) as n FROM task_events WHERE event_type = 'a2a_call'").get().n,
      avgDepth: this.db.prepare('SELECT AVG(depth) as avg FROM tasks WHERE parent_task_id IS NOT NULL').get().avg || 0,
      recentEvents: this.getTimeline({ limit: 20 }),
    };
  }

  failStaleActiveTasks({ originServer, olderThanMs = 0, reason = 'Task failed: server restarted while task was in progress' } = {}) {
    const conditions = ["state IN ('submitted', 'working')"];
    const params = [];
    if (originServer) {
      conditions.push('origin_server = ?');
      params.push(originServer);
    }
    if (olderThanMs > 0) {
      conditions.push("CAST(strftime('%s', updated_at) AS INTEGER) <= CAST(strftime('%s', 'now') AS INTEGER) - ?");
      params.push(Math.ceil(olderThanMs / 1000));
    }

    const rows = this.db.prepare(`
      SELECT id, origin_server
      FROM tasks
      WHERE ${conditions.join(' AND ')}
    `).all(...params);
    if (rows.length === 0) return 0;

    const update = this.db.prepare(`
      UPDATE tasks
      SET state = 'failed',
          error = ?,
          output_text = COALESCE(output_text, ?),
          updated_at = datetime('now')
      WHERE id = ?
    `);
    const tx = this.db.transaction((staleRows) => {
      for (const row of staleRows) {
        update.run(reason, reason, row.id);
      }
    });
    tx(rows);

    for (const row of rows) {
      this.createEvent(row.id, 'failed', row.origin_server || originServer || 'unknown', { outputPreview: reason });
    }
    return rows.length;
  }

  // ---- Canonical Context Snapshots ----

  upsertThread({ id, title, status = 'active', currentMode, currentTaskId, summary, metadata = {} }) {
    if (!id) throw new Error('thread id is required');
    const existing = this.getThread(id);
    const mergedMetadata = { ...(existing?.metadata || {}), ...(metadata || {}) };

    this.db.prepare(`
      INSERT INTO mesh_threads (id, title, status, current_mode, current_task_id, summary, metadata)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        title = COALESCE(excluded.title, mesh_threads.title),
        status = excluded.status,
        current_mode = COALESCE(excluded.current_mode, mesh_threads.current_mode),
        current_task_id = COALESCE(excluded.current_task_id, mesh_threads.current_task_id),
        summary = COALESCE(excluded.summary, mesh_threads.summary),
        metadata = excluded.metadata,
        updated_at = datetime('now')
    `).run(
      id,
      title || null,
      status,
      currentMode || null,
      currentTaskId || null,
      summary || null,
      JSON.stringify(mergedMetadata),
    );
    return this.getThread(id);
  }

  getThread(id) {
    const row = this.db.prepare('SELECT * FROM mesh_threads WHERE id = ?').get(id);
    if (!row) return null;
    return this._deserializeThread(row);
  }

  createContextSnapshot({
    id = randomUUID(),
    threadId,
    taskId,
    mode,
    title,
    summary,
    decisions = [],
    nextSteps = [],
    errors = [],
    artifacts = [],
    metadata = {},
  }) {
    if (!threadId) throw new Error('threadId is required');
    if (!mode) throw new Error('mode is required');
    if (!summary) throw new Error('summary is required');

    this.db.prepare(`
      INSERT INTO mesh_context_snapshots
        (id, thread_id, task_id, mode, title, summary, decisions, next_steps, errors, artifacts, metadata)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      id,
      threadId,
      taskId || null,
      mode,
      title || null,
      summary,
      JSON.stringify(decisions || []),
      JSON.stringify(nextSteps || []),
      JSON.stringify(errors || []),
      JSON.stringify(artifacts || []),
      JSON.stringify(metadata || {}),
    );

    this.upsertThread({
      id: threadId,
      title,
      currentMode: mode,
      currentTaskId: taskId,
      summary,
      metadata: { lastSnapshotId: id, ...(metadata || {}) },
    });

    return this.getContextSnapshot(id);
  }

  getContextSnapshot(id) {
    const row = this.db.prepare('SELECT * FROM mesh_context_snapshots WHERE id = ?').get(id);
    if (!row) return null;
    return this._deserializeContextSnapshot(row);
  }

  getLatestContextSnapshot({ threadId, mode } = {}) {
    const conditions = [];
    const params = [];
    let sql = 'SELECT * FROM mesh_context_snapshots';
    if (threadId) { conditions.push('thread_id = ?'); params.push(threadId); }
    if (mode) { conditions.push('mode = ?'); params.push(mode); }
    if (conditions.length > 0) sql += ` WHERE ${conditions.join(' AND ')}`;
    sql += ' ORDER BY created_at DESC, rowid DESC LIMIT 1';
    const row = this.db.prepare(sql).get(...params);
    if (!row) return null;
    return this._deserializeContextSnapshot(row);
  }

  listContextSnapshots({ threadId, mode, limit = 20 } = {}) {
    const conditions = [];
    const params = [];
    let sql = 'SELECT * FROM mesh_context_snapshots';
    if (threadId) { conditions.push('thread_id = ?'); params.push(threadId); }
    if (mode) { conditions.push('mode = ?'); params.push(mode); }
    if (conditions.length > 0) sql += ` WHERE ${conditions.join(' AND ')}`;
    sql += ' ORDER BY created_at DESC, rowid DESC LIMIT ?';
    params.push(parseInt(limit, 10) || 20);
    return this.db.prepare(sql).all(...params).map(r => this._deserializeContextSnapshot(r));
  }

  // ---- Internal ----

  _deserializeTask(row) {
    return {
      id: row.id,
      sessionId: row.session_id,
      originServer: row.origin_server,
      parentTaskId: row.parent_task_id,
      calledBy: row.called_by,
      meshChain: JSON.parse(row.mesh_chain || '[]'),
      depth: row.depth,
      state: row.state,
      inputText: row.input_text,
      outputText: row.output_text,
      error: row.error,
      providerSessionId: row.provider_session_id,
      providerSessionKey: row.provider_session_key,
      runtime: row.runtime,
      artifacts: JSON.parse(row.artifacts || '[]'),
      metadata: JSON.parse(row.metadata || '{}'),
      history: JSON.parse(row.history || '[]'),
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    };
  }

  _deserializeThread(row) {
    return {
      id: row.id,
      title: row.title,
      status: row.status,
      currentMode: row.current_mode,
      currentTaskId: row.current_task_id,
      summary: row.summary,
      metadata: JSON.parse(row.metadata || '{}'),
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    };
  }

  _deserializeContextSnapshot(row) {
    return {
      id: row.id,
      threadId: row.thread_id,
      taskId: row.task_id,
      mode: row.mode,
      title: row.title,
      summary: row.summary,
      decisions: JSON.parse(row.decisions || '[]'),
      nextSteps: JSON.parse(row.next_steps || '[]'),
      errors: JSON.parse(row.errors || '[]'),
      artifacts: JSON.parse(row.artifacts || '[]'),
      metadata: JSON.parse(row.metadata || '{}'),
      createdAt: row.created_at,
    };
  }

  close() {
    this.db.close();
  }
}
