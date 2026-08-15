import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

/**
 * Resolve the mesh bearer token without embedding it in CLI or MCP config.
 * An explicit environment value wins; otherwise every local component reads
 * the same user-private token file.
 */
export function loadA2AAuthToken({ env = process.env, home = os.homedir() } = {}) {
  const explicit = env.A2A_AUTH_TOKEN?.trim();
  if (explicit) return explicit;

  const tokenFile = env.A2A_AUTH_TOKEN_FILE || path.join(home, '.a2a', 'auth-token');
  try {
    return fs.readFileSync(tokenFile, 'utf8').trim();
  } catch {
    return '';
  }
}
