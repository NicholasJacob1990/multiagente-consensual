import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DEFAULT_MAX_ARTIFACT_BYTES = 100 * 1024 * 1024;
const DEFAULT_TEXT_PREVIEW_BYTES = 1024 * 1024;

const MIME_BY_EXTENSION = Object.freeze({
  '.md': 'text/markdown;charset=utf-8',
  '.txt': 'text/plain;charset=utf-8',
  '.json': 'application/json;charset=utf-8',
  '.yaml': 'application/yaml;charset=utf-8',
  '.yml': 'application/yaml;charset=utf-8',
  '.xml': 'application/xml;charset=utf-8',
  '.html': 'text/html;charset=utf-8',
  '.css': 'text/css;charset=utf-8',
  '.js': 'text/javascript;charset=utf-8',
  '.mjs': 'text/javascript;charset=utf-8',
  '.cjs': 'text/javascript;charset=utf-8',
  '.ts': 'text/typescript;charset=utf-8',
  '.tsx': 'text/typescript;charset=utf-8',
  '.jsx': 'text/javascript;charset=utf-8',
  '.py': 'text/x-python;charset=utf-8',
  '.java': 'text/x-java-source;charset=utf-8',
  '.go': 'text/x-go;charset=utf-8',
  '.rs': 'text/x-rust;charset=utf-8',
  '.sh': 'text/x-shellscript;charset=utf-8',
  '.sql': 'application/sql;charset=utf-8',
  '.pdf': 'application/pdf',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.doc': 'application/msword',
  '.odt': 'application/vnd.oasis.opendocument.text',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
});

function configuredLimit(name, fallback) {
  const value = Number.parseInt(String(process.env[name] || ''), 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function artifactStoreRoot() {
  const configured = String(process.env.A2A_ARTIFACT_STORE || '').trim();
  return path.resolve((configured || path.join(os.homedir(), '.local', 'state', 'a2a-mesh', 'artifacts')).replace(/^~/, os.homedir()));
}

export function mimeTypeForFile(filePath) {
  return MIME_BY_EXTENSION[path.extname(String(filePath || '')).toLowerCase()] || 'application/octet-stream';
}

function safeSegment(value, fallback) {
  const safe = String(value || '').replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 180);
  return safe || fallback;
}

function isTextMime(mime) {
  return /^text\//.test(mime) || /(?:json|yaml|xml|javascript|typescript|sql)/.test(mime);
}

export function preserveLocalFileArtifact(filePath, {
  taskId,
  agentId = 'mesh',
  description = '',
  source = 'declared-path',
} = {}) {
  if (!taskId) throw new Error('taskId is required to preserve a local artifact');
  const requested = String(filePath || '').trim().replace(/^~/, os.homedir());
  if (!requested) throw new Error('artifact path is empty');
  const resolved = fs.realpathSync(path.resolve(requested));
  const stat = fs.statSync(resolved);
  if (!stat.isFile()) throw new Error(`artifact path is not a regular file: ${resolved}`);
  const maxBytes = configuredLimit('A2A_ARTIFACT_MAX_BYTES', DEFAULT_MAX_ARTIFACT_BYTES);
  if (stat.size > maxBytes) throw new Error(`artifact exceeds ${maxBytes} bytes: ${resolved}`);

  const bytes = fs.readFileSync(resolved);
  const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
  const name = safeSegment(path.basename(resolved), 'artifact.bin');
  const taskSegment = safeSegment(taskId, 'task');
  const storeDir = path.join(artifactStoreRoot(), taskSegment);
  fs.mkdirSync(storeDir, { recursive: true, mode: 0o700 });
  const storedPath = path.join(storeDir, `${sha256}-${name}`);
  if (!fs.existsSync(storedPath)) {
    const temporary = path.join(storeDir, `.${sha256}-${process.pid}-${Date.now()}.tmp`);
    fs.writeFileSync(temporary, bytes, { mode: 0o600 });
    fs.renameSync(temporary, storedPath);
  }
  try { fs.chmodSync(storedPath, 0o600); } catch { /* best effort on non-POSIX filesystems */ }

  const mimeType = mimeTypeForFile(resolved);
  const parts = [{
    type: 'file',
    file: {
      uri: `a2a-artifact://${encodeURIComponent(taskSegment)}/${sha256}/${encodeURIComponent(name)}`,
      mimeType,
      name,
    },
  }];
  const previewLimit = configuredLimit('A2A_ARTIFACT_TEXT_PREVIEW_BYTES', DEFAULT_TEXT_PREVIEW_BYTES);
  if (isTextMime(mimeType) && bytes.length <= previewLimit) {
    parts.unshift({ type: 'text', text: bytes.toString('utf8'), mimeType });
  }

  return {
    name,
    description: description || `Arquivo preservado por ${agentId}`,
    parts,
    metadata: {
      kind: 'local-file',
      sha256,
      size: stat.size,
      mimeType,
      sourcePath: resolved,
      storedPath,
      source,
      agentId,
      taskId: String(taskId),
      preservedAt: new Date().toISOString(),
    },
  };
}

export function stripArtifactDeclarations(output) {
  return String(output || '').replace(/\n?\s*<artifact_path>[^<]+<\/artifact_path>\s*/gi, '\n').trim();
}

export function extractDeclaredFileArtifacts(output, options = {}) {
  const artifacts = [];
  const seen = new Set();
  const regex = /<artifact_path>\s*([^<]+?)\s*<\/artifact_path>/gi;
  let match;
  while ((match = regex.exec(String(output || ''))) !== null) {
    const declaredPath = match[1].trim();
    if (!declaredPath || seen.has(declaredPath)) continue;
    seen.add(declaredPath);
    try {
      artifacts.push(preserveLocalFileArtifact(declaredPath, {
        ...options,
        source: 'agent-declaration',
        description: options.description || 'Arquivo declarado pelo agente como produto da tarefa',
      }));
    } catch (error) {
      if (process.env.A2A_DEBUG === 'true') console.warn('[artifact] ignored declaration:', error.message);
    }
  }
  return artifacts;
}

export function extractResponseArtifacts(output, options = {}) {
  const codeArtifacts = [];
  const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
  let match;
  while ((match = codeBlockRegex.exec(String(output || ''))) !== null) {
    codeArtifacts.push({
      name: match[1] ? `code.${match[1]}` : 'code-snippet',
      description: `Bloco de codigo ${match[1] || ''}`.trim(),
      parts: [{ type: 'text', text: match[2].trim() }],
      metadata: { kind: 'embedded-text', agentId: options.agentId || 'mesh', taskId: options.taskId || null },
    });
  }
  return mergeArtifacts(codeArtifacts, extractDeclaredFileArtifacts(output, options));
}

export function mergeArtifacts(...collections) {
  const merged = [];
  const seen = new Set();
  for (const artifact of collections.flat().filter(Boolean)) {
    const key = artifact?.metadata?.sha256
      ? `sha256:${artifact.metadata.sha256}:${artifact.name || ''}`
      : `content:${artifact?.name || ''}:${artifact?.parts?.map(part => part?.text || part?.file?.uri || '').join('|') || ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(artifact);
  }
  return merged;
}

export function resolveStoredArtifact(artifact) {
  if (artifact?.metadata?.kind !== 'local-file') return null;
  const storedPath = String(artifact.metadata.storedPath || '');
  if (!storedPath) return null;
  const root = fs.realpathSync(artifactStoreRoot());
  const resolved = fs.realpathSync(storedPath);
  const relative = path.relative(root, resolved);
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('artifact storage path escaped the artifact root');
  const stat = fs.statSync(resolved);
  if (!stat.isFile()) throw new Error('stored artifact is not a regular file');
  const actualHash = crypto.createHash('sha256').update(fs.readFileSync(resolved)).digest('hex');
  if (actualHash !== artifact.metadata.sha256) throw new Error('stored artifact hash mismatch');
  return {
    path: resolved,
    name: artifact.name || path.basename(resolved),
    mimeType: artifact.metadata.mimeType || mimeTypeForFile(resolved),
    size: stat.size,
    sha256: actualHash,
  };
}
