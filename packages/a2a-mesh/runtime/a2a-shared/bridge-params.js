function governedContext(context = {}, targets = []) {
  const depth = Number.parseInt(String(context.depth ?? 7), 10);
  const meshChain = Array.isArray(context.meshChain)
    ? context.meshChain.filter((item) => typeof item === 'string' && item)
    : [];
  if (!Number.isFinite(depth) || depth <= 0) {
    throw new Error(`max mesh depth exceeded (chain: ${meshChain.join(' → ') || 'empty'})`);
  }
  const repeated = [...new Set(targets.filter((target) => meshChain.includes(target)))];
  if (repeated.length > 0) {
    throw new Error(`mesh loop detected for ${repeated.join(', ')} (chain: ${meshChain.join(' → ')})`);
  }
  return { depth, meshChain };
}

export function callBridgeParams(args = {}, context = {}) {
  return {
    agent: args.agent,
    prompt: args.prompt,
    ...governedContext(context, [args.agent]),
  };
}

export function broadcastBridgeParams(args = {}, context = {}) {
  const agents = Array.isArray(args.agents) ? args.agents : [];
  return {
    prompt: args.prompt,
    agents: args.agents,
    includeSelf: true,
    ...governedContext(context, agents),
  };
}

export function teamBridgeParams(args = {}, context = {}) {
  const agents = Array.isArray(args.steps)
    ? args.steps.flatMap((step) => Array.isArray(step?.agents) ? step.agents : [])
    : [];
  return {
    name: args.name,
    steps: args.steps,
    context: args.context,
    ...governedContext(context, agents),
  };
}

export function debateBridgeParams(args = {}, context = {}) {
  const targets = [...(Array.isArray(args.agents) ? args.agents : []), args.judge].filter(Boolean);
  return {
    topic: args.topic,
    rounds: Math.min(args.rounds || 4, 36),
    agents: args.agents,
    judge: args.judge,
    ...governedContext(context, targets),
  };
}

export function planBridgeParams(args = {}, context = {}) {
  const targets = [args.author, args.reviewer].filter(Boolean);
  return {
    description: args.description,
    author: args.author,
    reviewer: args.reviewer,
    rounds: Math.min(args.rounds || 3, 36),
    lenses: args.lenses,
    ...governedContext(context, targets),
  };
}

export function consensusBridgeParams(args = {}, context = {}) {
  const targets = [...(Array.isArray(args.agents) ? args.agents : []), args.judge].filter(Boolean);
  const governed = governedContext(context, targets);
  return {
    prompt: args.prompt,
    agents: args.agents,
    judge: args.judge,
    quorum: args.quorum,
    ...governed,
  };
}

export function ensembleBridgeParams(args = {}, context = {}) {
  const targets = [...(Array.isArray(args.agents) ? args.agents : []), args.judge].filter(Boolean);
  const governed = governedContext(context, targets);
  return {
    task: args.task,
    language: args.language || 'python',
    rounds: Math.min(args.rounds || 1, 12),
    agents: args.agents,
    judge: args.judge,
    ...governed,
  };
}
