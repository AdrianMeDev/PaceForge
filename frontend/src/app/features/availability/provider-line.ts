import { AiProviderState } from '../../core/coach/coach-models';

/** What the page says when the setup could not be read. */
export const UNKNOWN_PROVIDER = 'your AI provider';

/**
 * Where what the user allows goes, in a few words: the provider and the model they set up, with
 * the host of an OpenAI-compatible address. Only what the setup shows, never the key.
 */
export function providerLine(state: AiProviderState | null): string {
  if (state === null) {
    return UNKNOWN_PROVIDER;
  }
  if (!state.configured || state.provider === null) {
    return 'no AI provider is set up yet, so nothing is sent';
  }
  const model = state.model ? `, model ${state.model}` : '';
  if (state.provider === 'anthropic') {
    return `Anthropic${model}`;
  }
  const host = hostOf(state.base_url);
  return `an OpenAI-compatible service${host ? ` at ${host}` : ''}${model}`;
}

function hostOf(address: string | null): string | null {
  if (address === null) {
    return null;
  }
  try {
    return new URL(address).host || null;
  } catch {
    return null;
  }
}
