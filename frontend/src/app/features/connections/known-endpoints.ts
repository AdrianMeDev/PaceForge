/**
 * Names for the addresses that operators are most likely to allow, so that the form can say
 * "DeepSeek (https://api.deepseek.com)" instead of only the address. The name is a label and
 * nothing more: what a user chooses and what is saved is the plain address, and which addresses
 * may be chosen at all is the operator's list.
 */
const KNOWN: Record<string, string> = {
  'https://api.deepseek.com': 'DeepSeek',
  'https://api.deepseek.com/v1': 'DeepSeek',
  'https://openrouter.ai/api/v1': 'OpenRouter',
  'https://api.openai.com/v1': 'OpenAI',
  'http://localhost:11434/v1': 'Ollama (this machine)',
};

/** The name of a well-known address, `null` for any other. */
export function endpointLabel(address: string): string | null {
  const normal = normalForm(address);
  return normal === null ? null : (KNOWN[normal] ?? null);
}

/** The form the server compares: lower-case host, default port left out, no trailing slash. */
function normalForm(address: string): string | null {
  try {
    const url = new URL(address);
    if (url.search !== '' || url.hash !== '' || url.username !== '' || url.password !== '') {
      return null;
    }
    return `${url.protocol}//${url.host}${url.pathname.replace(/\/+$/, '')}`;
  } catch {
    return null;
  }
}
