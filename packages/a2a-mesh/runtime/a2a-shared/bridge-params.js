export function consensusBridgeParams(args = {}, context = {}) {
  return {
    prompt: args.prompt,
    agents: args.agents,
    judge: args.judge,
    quorum: args.quorum,
    depth: context.depth,
    meshChain: context.meshChain,
  };
}

export function ensembleBridgeParams(args = {}, context = {}) {
  return {
    task: args.task,
    language: args.language || 'python',
    rounds: Math.min(args.rounds || 1, 12),
    agents: args.agents,
    judge: args.judge,
    depth: context.depth,
    meshChain: context.meshChain,
  };
}
