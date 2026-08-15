// Propagate mesh recursion governance into provider CLIs that can invoke the MCP bridge.

export function bridgeEnvironmentForTask(task, selfId, baseEnvironment = process.env) {
  const env = { ...baseEnvironment };
  const parsedDepth = Number.parseInt(String(task?.metadata?.maxDepth ?? env.A2A_MESH_MAX_DEPTH ?? 7), 10);
  const depth = Number.isFinite(parsedDepth) ? parsedDepth : 7;
  const chain = Array.isArray(task?.metadata?.meshChain) ? task.metadata.meshChain : [];
  env.A2A_MESH_BRIDGE_REMAINING_DEPTH = String(Math.max(0, depth - 1));
  env.A2A_MESH_BRIDGE_CHAIN = JSON.stringify([...chain, selfId]);
  env.A2A_MESH_BRIDGE_CALLER = selfId;
  return env;
}
