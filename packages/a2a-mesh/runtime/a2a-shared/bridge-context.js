// Propagate mesh recursion governance into provider CLIs that can invoke the MCP bridge.

export function bridgeEnvironmentForTask(task, selfId, baseEnvironment = process.env) {
  const env = { ...baseEnvironment };
  const parsedDepth = Number.parseInt(String(task?.metadata?.maxDepth ?? env.A2A_MESH_MAX_DEPTH ?? 7), 10);
  const depth = Number.isFinite(parsedDepth) ? parsedDepth : 7;
  const chain = Array.isArray(task?.metadata?.meshChain)
    ? task.metadata.meshChain.filter((item) => typeof item === 'string' && item)
    : [];
  const forwardedChain = chain[chain.length - 1] === selfId ? chain : [...chain, selfId];
  // The bridge submits the next mesh call; the receiving mesh caller performs
  // the single decrement for that hop. Subtracting here as well would consume
  // two depth units for one delegation.
  env.A2A_MESH_BRIDGE_REMAINING_DEPTH = String(Math.max(0, depth));
  env.A2A_MESH_BRIDGE_CHAIN = JSON.stringify(forwardedChain);
  env.A2A_MESH_BRIDGE_CALLER = selfId;
  return env;
}
