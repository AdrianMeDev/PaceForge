import { AiProviderState } from '../../core/coach/coach-models';
import { UNKNOWN_PROVIDER, providerLine } from './provider-line';

const BASE: AiProviderState = {
  configured: true,
  provider: 'anthropic',
  model: 'claude-sonnet-5-5',
  season_model: '',
  week_model: '',
  chat_model: '',
  base_url: null,
  has_key: true,
  status: 'connected',
  last_checked_at: null,
  last_success_at: null,
  allowed_base_urls: [],
  usage: {
    calls: 0,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    days: 30,
  },
};

describe('providerLine', () => {
  it('names Anthropic and the model', () => {
    expect(providerLine(BASE)).toBe('Anthropic, model claude-sonnet-5-5');
  });

  it('names an OpenAI-compatible service with the host of its address', () => {
    const state: AiProviderState = {
      ...BASE,
      provider: 'openai_compatible',
      model: 'llama3.1:8b',
      base_url: 'http://localhost:11434/v1',
    };

    expect(providerLine(state)).toBe(
      'an OpenAI-compatible service at localhost:11434, model llama3.1:8b',
    );
  });

  it('leaves out an address it cannot read and never shows the path', () => {
    const odd: AiProviderState = { ...BASE, provider: 'openai_compatible', base_url: 'not a url' };
    const secret: AiProviderState = {
      ...BASE,
      provider: 'openai_compatible',
      base_url: 'https://api.example.com/v1/secret-path',
    };

    expect(providerLine(odd)).toBe('an OpenAI-compatible service, model claude-sonnet-5-5');
    expect(providerLine(secret)).not.toContain('secret-path');
    expect(providerLine(secret)).toContain('api.example.com');
  });

  it('leaves out an empty model name', () => {
    expect(providerLine({ ...BASE, model: '' })).toBe('Anthropic');
  });

  it('says that nothing is sent when no provider is set up', () => {
    const none: AiProviderState = { ...BASE, configured: false, provider: null, model: '' };

    expect(providerLine(none)).toBe('no AI provider is set up yet, so nothing is sent');
  });

  it('says so in general when the setup could not be read', () => {
    expect(providerLine(null)).toBe(UNKNOWN_PROVIDER);
    expect(UNKNOWN_PROVIDER).toBe('your AI provider');
  });
});
