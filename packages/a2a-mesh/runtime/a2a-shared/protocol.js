// ============================================
// Protocol Version Constants
// ============================================
// Centralized protocol versioning for A2A mesh communication.

export const A2A_PROTOCOL_VERSION = '1.0';
export const A2A_MIN_SUPPORTED_VERSION = '1.0';
export const A2A_VERSION_HEADER = 'A2A-Protocol-Version';

/**
 * Compare two semver-like version strings (major.minor).
 * Returns true if the given version is compatible with our minimum supported version.
 */
export function isVersionCompatible(version) {
  if (!version || typeof version !== 'string') return true; // missing = assume compatible
  const [major, minor] = version.split('.').map(Number);
  const [minMajor, minMinor] = A2A_MIN_SUPPORTED_VERSION.split('.').map(Number);
  if (major !== minMajor) return false; // major mismatch = incompatible
  return minor >= minMinor;
}

/**
 * Log a warning if the peer's protocol version is incompatible.
 * Does NOT reject — forward compatibility by design.
 */
export function checkVersionHeader(req) {
  const peerVersion = req.headers?.[A2A_VERSION_HEADER.toLowerCase()];
  if (peerVersion && !isVersionCompatible(peerVersion)) {
    console.warn(`[protocol] Incompatible protocol version from peer: ${peerVersion} (supported: >=${A2A_MIN_SUPPORTED_VERSION})`);
  }
  return peerVersion || null;
}
