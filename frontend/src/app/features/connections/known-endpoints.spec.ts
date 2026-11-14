import { endpointLabel } from './known-endpoints';

describe('endpointLabel', () => {
  it.each([
    ['https://api.deepseek.com', 'DeepSeek'],
    ['https://api.deepseek.com/v1', 'DeepSeek'],
    ['https://openrouter.ai/api/v1', 'OpenRouter'],
    ['https://api.openai.com/v1', 'OpenAI'],
    ['http://localhost:11434/v1', 'Ollama (this machine)'],
  ])('names %s as %s', (address, name) => {
    expect(endpointLabel(address)).toBe(name);
  });

  it.each([
    ['a trailing slash', 'https://api.deepseek.com/'],
    ['several trailing slashes', 'https://api.deepseek.com/v1//'],
    ['capital letters in the host', 'https://API.DeepSeek.com'],
    ['the default port', 'https://api.deepseek.com:443'],
  ])('knows an address with %s', (_name, address) => {
    expect(endpointLabel(address)).toBe('DeepSeek');
  });

  it.each([
    ['a lookalike host', 'https://api.deepseek.com.evil.example/v1'],
    ['the name in the path of another host', 'https://evil.example/api.deepseek.com'],
    ['another scheme', 'http://api.deepseek.com'],
    ['another port', 'https://api.deepseek.com:8443'],
    ['another path', 'https://api.deepseek.com/other'],
    ['the path in other letters (the server compares it exactly)', 'https://api.deepseek.com/V1'],
    ['a sub-domain', 'https://eu.api.deepseek.com'],
    ['another port for Ollama', 'http://localhost:8080/v1'],
    ['a query', 'https://api.deepseek.com?x=1'],
    ['a fragment', 'https://api.deepseek.com#x'],
    ['a user name', 'https://user@api.deepseek.com'],
    ['a password', 'https://user:secret@api.deepseek.com'],
    ['an address that is none', 'not an address'],
    ['an empty text', ''],
  ])('does not name %s', (_name, address) => {
    expect(endpointLabel(address)).toBeNull();
  });

  it('leaves the address that is a user name with a password out of the answer', () => {
    expect(JSON.stringify(endpointLabel('https://user:secret@api.deepseek.com'))).not.toContain(
      'secret',
    );
  });
});
