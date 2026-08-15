// ============================================
// Task States — Centralized state definitions
// ============================================

/**
 * All valid A2A task states.
 */
export const VALID_STATES = new Set([
  'submitted',
  'working',
  'completed',
  'failed',
  'canceled',
  'input_required',
  'rejected',
  'auth_required',
]);

/**
 * Terminal states — task is done and won't change again.
 * These can be evicted and trigger push notifications.
 */
export const TERMINAL_STATES = new Set([
  'completed',
  'failed',
  'canceled',
  'rejected',
]);

/**
 * Waiting states — task is paused, waiting for external input.
 * Should NOT be marked as zombie on restart (they're not actively processing).
 * Should NOT be evicted (they may resume).
 */
export const WAITING_STATES = new Set([
  'input_required',
  'auth_required',
]);

/**
 * Active states — task is actively being processed.
 * These count toward concurrency limits.
 * On restart, these are zombies (no running process) and should be marked as failed.
 */
export const ACTIVE_STATES = new Set([
  'submitted',
  'working',
]);
