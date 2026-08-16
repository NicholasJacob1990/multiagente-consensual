// ============================================
// CLI Tool Wrapper — A2A tool support for CLI mode
// ============================================
// Injects tool descriptions into prompts and parses
// structured tool calls from CLI output.

/**
 * Build a text prefix describing available A2A tools.
 * Injected into the CLI prompt so the model knows how to invoke them.
 */
export function buildA2AToolPrefix(peers, depth) {
  const artifactRule = `[A2A ARTIFACT REGISTRATION]
When you create or materially modify a local file that is a deliverable, add one declaration per file at the very end of your final answer:
<artifact_path>/absolute/path/to/file.ext</artifact_path>
Declare only files you created or changed for this task. Never declare files merely inspected or pre-existing unchanged files.
[END A2A ARTIFACT REGISTRATION]\n\n`;

  if (depth <= 0 || !peers || Object.keys(peers).length === 0) return artifactRule;

  const peerList = Object.keys(peers).join(', ');

  return `[AVAILABLE A2A TOOLS]
You can collaborate with other AI agents. To invoke a tool, output a JSON block wrapped in <tool_call> tags on its own line.

1. a2a_call — Call one agent (${peerList})
   <tool_call>{"name":"a2a_call","input":{"agent":"AGENT_ID","prompt":"your question"}}</tool_call>

2. a2a_broadcast — Call multiple agents in parallel
   <tool_call>{"name":"a2a_broadcast","input":{"prompt":"question for all"}}</tool_call>

3. a2a_team — Multi-step workflow (parallel/sequential)
   <tool_call>{"name":"a2a_team","input":{"name":"workflow","steps":[{"mode":"parallel","agents":["${peerList.split(', ')[0]}"],"prompt":"task"}]}}</tool_call>

RULES:
- Output ONLY ONE <tool_call> block at a time
- Put the block on its own line with no other text on that line
- Wait for the tool result before continuing
- If you don't need a tool, respond normally without any <tool_call> tags
[END A2A TOOLS]

${artifactRule}`;
}

/**
 * Parse the first <tool_call> block from CLI output.
 * Returns { name, input, raw, beforeCall, afterCall } or null.
 */
export function parseToolCall(output) {
  const match = output.match(/<tool_call>\s*([\s\S]*?)\s*<\/tool_call>/);
  if (!match) return null;

  try {
    const parsed = JSON.parse(match[1].trim());
    const idx = output.indexOf(match[0]);
    return {
      name: parsed.name,
      input: parsed.input || parsed.args || {},
      raw: match[0],
      beforeCall: output.slice(0, idx).trim(),
      afterCall: output.slice(idx + match[0].length).trim(),
    };
  } catch {
    return null;
  }
}

/**
 * Remove all <tool_call> blocks from output text.
 */
export function removeToolCalls(output) {
  return output.replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '').trim();
}

/**
 * Incrementally removes custom <tool_call> blocks from CLI progress streams.
 *
 * The full response is parsed only after the process exits, but progress is
 * forwarded while the model is still writing. Without a stateful filter the
 * dashboard exposes JSON tool payloads (and sometimes half of a split tag)
 * before removeToolCalls() can clean the final response.
 */
export function createToolCallStreamFilter() {
  const OPEN = '<tool_call';
  const CLOSE = '</tool_call>';
  let pending = '';
  let suppressing = false;

  function longestOpenPrefixSuffix(value) {
    const max = Math.min(value.length, OPEN.length - 1);
    for (let length = max; length > 0; length -= 1) {
      if (OPEN.startsWith(value.slice(-length))) return length;
    }
    return 0;
  }

  return {
    push(chunk) {
      pending += String(chunk || '');
      let visible = '';

      while (pending) {
        if (suppressing) {
          const closeIndex = pending.indexOf(CLOSE);
          if (closeIndex < 0) {
            // Retain only enough tail to recognize a closing tag split across
            // chunks; the tool payload itself must never reach the UI.
            pending = pending.slice(-Math.max(0, CLOSE.length - 1));
            break;
          }
          pending = pending.slice(closeIndex + CLOSE.length);
          suppressing = false;
          continue;
        }

        const openIndex = pending.indexOf(OPEN);
        if (openIndex >= 0) {
          visible += pending.slice(0, openIndex);
          pending = pending.slice(openIndex + OPEN.length);
          suppressing = true;
          continue;
        }

        const retained = longestOpenPrefixSuffix(pending);
        const emitLength = pending.length - retained;
        if (emitLength > 0) visible += pending.slice(0, emitLength);
        pending = pending.slice(emitLength);
        break;
      }

      return visible;
    },

    flush() {
      if (suppressing) {
        pending = '';
        return '';
      }
      const visible = pending;
      pending = '';
      return visible;
    },
  };
}

// Patterns that mark CLI bootstrap noise — never the model's actual answer.
// Each pattern strips a single line; the codex header block (between '--------'
// fences) is handled separately because it spans multiple lines.
const BOOTSTRAP_LINE_RE = /^(?:Reading additional input from stdin\.\.\.|.*ERROR rmcp::transport::worker:.*|.*MallocStackLogging:.*|Skill conflict detected:.*|Skill ".*" from ".*" is overriding.*|Warning: Could not read directory .*: EACCES.*|Warning: 256-color support not detected\..*|Ripgrep is not available\..*|YOLO mode is enabled\..*|Attempt \d+ failed with status \d+\..*|OpenAI Codex v[\d.\-a-z]+(?: \(research preview\))?|Gemini CLI v[\d.\-a-z]+|user|assistant)$/;

// Codex CLI prints a header block fenced by '--------' containing workdir/model/session.
// The block ends with a line of dashes, after which the prompt is echoed under 'user'.
// Strip from the first opening fence to the line *before* meaningful content.
function stripCodexHeaderBlock(text) {
  const lines = text.split('\n');
  const out = [];
  let inHeader = false;
  let sawHeaderClose = false;
  let inPromptEcho = false;
  for (const line of lines) {
    if (!sawHeaderClose && /^-{8,}$/.test(line.trim())) {
      inHeader = !inHeader;
      if (!inHeader) sawHeaderClose = true;
      continue;
    }
    if (inHeader) continue;
    if (sawHeaderClose && !inPromptEcho && /^user\s*$/.test(line)) {
      inPromptEcho = true;
      continue;
    }
    if (inPromptEcho) {
      // Prompt echo runs until '[END A2A TOOLS]' or empty separator + content
      if (/\[END A2A TOOLS\]/.test(line)) { inPromptEcho = false; continue; }
      continue;
    }
    out.push(line);
  }
  return out.join('\n');
}

/**
 * Strip CLI bootstrap noise (transport errors, headers, prompt echo, warnings).
 * Use this on raw CLI stdout before treating it as the agent's answer.
 */
export function sanitizeCliBootstrap(rawOutput) {
  if (!rawOutput) return '';
  let text = stripCodexHeaderBlock(String(rawOutput));
  text = text
    .split('\n')
    .filter(line => !BOOTSTRAP_LINE_RE.test(line))
    .join('\n')
    .trim();
  return text;
}

/**
 * Heuristic: did the CLI output ONLY bootstrap noise (no real answer)?
 * Returns true ONLY when sanitization actually stripped bootstrap patterns
 * AND what remains is tiny. Plain short content (e.g. "ok" or short snippets)
 * is NOT bootstrap because sanitize wouldn't change it.
 */
export function isOnlyBootstrap(rawOutput) {
  const original = String(rawOutput || '').trim();
  if (original.length === 0) return true;
  const cleaned = sanitizeCliBootstrap(rawOutput);
  // Sanitize removed something AND what's left is below the noise floor.
  return cleaned.length < 20 && cleaned.length < original.length;
}

// Capacity-exhaustion patterns from Google Vertex / CloudCode 429 responses.
// When any of these appears in stderr/stdout DURING streaming, the CLI is
// internally retrying (Attempt 1, Attempt 2, ...) and will burn ~15min before
// giving up. Detecting early lets the parent kill the child and switch models.
const CAPACITY_ERROR_PATTERNS = Object.freeze([
  'MODEL_CAPACITY_EXHAUSTED',
  'RESOURCE_EXHAUSTED',
  'No capacity available',
]);

/**
 * Returns true if the chunk contains a Google capacity-exhausted error code.
 * Use this on stderr/stdout chunks to fail-fast instead of waiting for the
 * CLI's internal retry loop to give up.
 */
export function hasCapacityError(text) {
  if (typeof text !== 'string' || text.length === 0) return false;
  return CAPACITY_ERROR_PATTERNS.some(p => text.includes(p));
}

/**
 * Detects whether a CLI response is mostly an echo of the input prompt rather
 * than a real generation. This happens when the codex/gemini CLI starts up,
 * prints the session banner, echoes the prompt under "user", and exits without
 * generating anything (e.g. on rmcp transport failure or silent quota error).
 *
 * The check looks for any long contiguous window of the prompt (≥ minWindow
 * chars) that appears verbatim in the response. Real responses never copy the
 * prompt that closely — they paraphrase or quote short fragments at most.
 *
 * Returns true if the response is mostly an echo (or empty after sanitize).
 */
export function looksLikePromptEcho(response, prompt, { minWindow = 60, sampleStep = 20 } = {}) {
  if (typeof response !== 'string' || typeof prompt !== 'string') return false;
  // Only flag echo when sanitize stripped real bootstrap noise AND nothing
  // substantive remains. Short legitimate responses ("ok", "done", a tiny
  // code snippet) are NOT echoes — handle them at the caller level if needed.
  if (isOnlyBootstrap(response)) return true;
  const cleaned = sanitizeCliBootstrap(response).replace(/\s+/g, ' ').trim();
  const promptStripped = prompt.replace(/\s+/g, ' ').trim();
  if (promptStripped.length < minWindow || cleaned.length < minWindow) return false;
  // Slide a window across the prompt; if any window appears in the response,
  // the model regurgitated the prompt instead of generating an answer.
  for (let i = 0; i + minWindow <= promptStripped.length; i += sampleStep) {
    const window = promptStripped.slice(i, i + minWindow);
    if (cleaned.includes(window)) return true;
  }
  return false;
}

/**
 * Classify an ensemble/agent submission so downstream phases (REVIEW, REVISE)
 * can short-circuit instead of feeding garbage forward.
 *
 * Returns one of:
 *   'ok'           — substantive content, proceed
 *   'empty'        — empty/whitespace after sanitize
 *   'mesh-error'   — starts with mesh "Error: ..." string
 *   'bootstrap'    — only CLI banner / prompt echo / warnings
 *   'prompt-echo'  — contains a long verbatim slice of the prompt
 */
export function classifySubmission(response, prompt) {
  const text = typeof response === 'string' ? response.trim() : '';
  if (text.length === 0) return 'empty';
  if (/^(Error\s+from\s|Error:|Unknown agent:|No response received from agent)/i.test(text)) {
    return 'mesh-error';
  }
  if (isOnlyBootstrap(text)) return 'bootstrap';
  if (looksLikePromptEcho(text, prompt)) return 'prompt-echo';
  return 'ok';
}

/**
 * Build a follow-up prompt with tool result for next CLI round.
 */
export function buildFollowUpPrompt(originalPrompt, previousOutput, toolName, toolResult) {
  return `${originalPrompt}

[Your previous response]
${removeToolCalls(previousOutput)}

[Tool "${toolName}" returned]
${String(toolResult ?? '').slice(0, 100000)}

Continue your response incorporating the tool result above. If you need another tool, use <tool_call> again. Otherwise respond normally.`;
}
