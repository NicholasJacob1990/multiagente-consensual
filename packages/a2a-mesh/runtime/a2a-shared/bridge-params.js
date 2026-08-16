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

function profiledRounds(args, defaults, fallback, cap) {
  const explicit = Number.parseInt(String(args.rounds ?? ''), 10);
  if (Number.isFinite(explicit) && explicit > 0) return Math.min(explicit, cap);
  const profile = String(args.profile || '').trim().toLowerCase();
  return defaults[profile] || fallback;
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
    recursive: args.recursive === true,
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
    ...(args.profile ? { profile: args.profile } : {}),
    ...governedContext(context, agents),
  };
}

export function debateBridgeParams(args = {}, context = {}) {
  const targets = [...(Array.isArray(args.agents) ? args.agents : []), args.judge].filter(Boolean);
  return {
    topic: args.topic,
    rounds: profiledRounds(args, { fast: 2, normal: 4, deep: 8 }, 4, 36),
    agents: args.agents,
    judge: args.judge,
    ...(args.profile ? { profile: args.profile } : {}),
    ...governedContext(context, targets),
  };
}

export function planBridgeParams(args = {}, context = {}) {
  const targets = [args.author, args.reviewer].filter(Boolean);
  return {
    description: args.description,
    author: args.author,
    reviewer: args.reviewer,
    rounds: profiledRounds(args, { fast: 1, normal: 3, deep: 6 }, 3, 36),
    lenses: args.lenses,
    ...(args.profile ? { profile: args.profile } : {}),
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
    ...(args.profile ? { profile: args.profile } : {}),
    ...governed,
  };
}

export function ensembleBridgeParams(args = {}, context = {}) {
  const targets = [...(Array.isArray(args.agents) ? args.agents : []), args.judge].filter(Boolean);
  const governed = governedContext(context, targets);
  const result = {
    task: args.task,
    language: args.language || 'python',
    agents: args.agents,
    judge: args.judge,
    ...(args.profile ? { profile: args.profile } : {}),
    ...(args.deduplicate != null ? { deduplicate: args.deduplicate } : {}),
    ...((args.early_exit ?? args.earlyExit) != null ? { early_exit: args.early_exit ?? args.earlyExit } : {}),
    ...governed,
  };
  if (args.rounds != null) result.rounds = Math.min(args.rounds, 12);
  else if (!args.profile) result.rounds = 1;
  return result;
}
