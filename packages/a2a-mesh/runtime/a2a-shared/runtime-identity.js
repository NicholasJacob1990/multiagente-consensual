export const A2A_MANAGED_RUNTIME_OWNER = '@nicholasjacob90/a2a-mesh';

export function managedRuntimeIdentity(agentId) {
  return {
    owner: A2A_MANAGED_RUNTIME_OWNER,
    agentId: String(agentId || ''),
  };
}

export function isManagedAgentHealth(health, expectedAgentId) {
  if (!health || health.status !== 'ok') return false;
  if (!expectedAgentId) return true;
  return health.runtimeIdentity?.owner === A2A_MANAGED_RUNTIME_OWNER
    && health.runtimeIdentity?.agentId === expectedAgentId;
}
