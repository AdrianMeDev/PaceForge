import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CoachApi } from '../../core/coach/coach-api';
import {
  AiProviderInput,
  AiProviderState,
  CheckProviderResult,
  GetProviderResult,
  RemoveProviderResult,
  SaveProviderResult,
} from '../../core/coach/coach-models';
import { dayOf, query, required, settle, typeInto } from '../../testing/dom';
import { AiProviderPanel } from './ai-provider-panel';

const KEY = 'sk-ant-test-0123456789-abcdefghij';
const OTHER_KEY = 'sk-ant-other-9876543210-zyxwvutsrq';
const LOCAL = 'http://localhost:11434/v1';
const OPENAI = 'https://api.openai.com/v1';

const NOT_SET_UP: AiProviderState = {
  configured: false,
  provider: null,
  model: '',
  base_url: null,
  has_key: false,
  status: null,
  last_checked_at: null,
  last_success_at: null,
  allowed_base_urls: [],
  usage: { calls: 0, input_tokens: 0, output_tokens: 0, days: 30 },
};
const ANTHROPIC: AiProviderState = {
  ...NOT_SET_UP,
  configured: true,
  provider: 'anthropic',
  model: 'claude-sonnet-5-5',
  has_key: true,
  status: 'untested',
};
const CONNECTED: AiProviderState = {
  ...ANTHROPIC,
  status: 'connected',
  last_checked_at: '2026-11-13T12:00:00Z',
  last_success_at: '2026-11-13T12:00:00Z',
  usage: { calls: 1234, input_tokens: 9000, output_tokens: 1, days: 30 },
};
const COMPATIBLE: AiProviderState = {
  ...NOT_SET_UP,
  configured: true,
  provider: 'openai_compatible',
  model: 'llama3.1:8b',
  base_url: LOCAL,
  has_key: false,
  status: 'untested',
  allowed_base_urls: [LOCAL, OPENAI],
};

const ok = (state: AiProviderState): GetProviderResult => ({ kind: 'ok', state });
const saved = (state: AiProviderState): SaveProviderResult => ({ kind: 'ok', state });

function createApiStub() {
  return {
    get: vi.fn<() => Promise<GetProviderResult>>(),
    save: vi.fn<(input: AiProviderInput) => Promise<SaveProviderResult>>(),
    remove: vi.fn<() => Promise<RemoveProviderResult>>(),
    check: vi.fn<() => Promise<CheckProviderResult>>(),
  };
}

function deferred<T>() {
  let resolve!: (result: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('AiProviderPanel', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<AiProviderPanel>;
  let panel: HTMLElement;
  let events: string[];

  async function setup(first: GetProviderResult = ok(NOT_SET_UP)) {
    TestBed.resetTestingModule(); // a test may set up a second situation
    api = createApiStub();
    api.get.mockResolvedValue(first);
    TestBed.configureTestingModule({
      imports: [AiProviderPanel],
      providers: [{ provide: CoachApi, useValue: api }],
    });
    fixture = TestBed.createComponent(AiProviderPanel);
    events = [];
    fixture.componentInstance.signedOut.subscribe(() => events.push('signedOut'));
    panel = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => panel.textContent ?? '';
  const alerts = () =>
    Array.from(panel.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const testId = (id: string) =>
    query(panel, `[data-testid="${id}"]`).textContent?.replace(/\s+/g, ' ').trim();
  const has = (selector: string) => panel.querySelector(selector) !== null;
  const value = (selector: string) =>
    query<HTMLInputElement | HTMLSelectElement>(panel, selector).value;
  const optionTexts = (selector: string) =>
    Array.from(panel.querySelectorAll(`${selector} option`)).map((o) =>
      (o.textContent ?? '').replace(/\s+/g, ' ').trim(),
    );

  function button(label: string): HTMLButtonElement {
    const match = Array.from(panel.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').trim().includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(label: string): Promise<void> {
    button(label).click();
    await settle(fixture);
  }

  async function type(selector: string, input: string): Promise<void> {
    typeInto(panel, selector, input);
    await settle(fixture);
  }

  async function choose(selector: string, chosen: string): Promise<void> {
    const select = query<HTMLSelectElement>(panel, selector);
    select.value = chosen;
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
  }

  async function submit(): Promise<void> {
    query<HTMLFormElement>(panel, 'form').dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the setup arrives', () => {
      api = createApiStub();
      api.get.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [AiProviderPanel],
        providers: [{ provide: CoachApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AiProviderPanel);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('form')).toBeNull();
    });

    it('asks once', async () => {
      await setup();

      expect(api.get).toHaveBeenCalledTimes(1);
    });

    it('offers a retry when the setup cannot be loaded', async () => {
      api = createApiStub();
      api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok(ANTHROPIC));
      TestBed.configureTestingModule({
        imports: [AiProviderPanel],
        providers: [{ provide: CoachApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AiProviderPanel);
      panel = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your AI provider could not be loaded.']);

      await click('Try again');

      expect(alerts()).toEqual([]);
      expect(testId('model')).toBe('claude-sonnet-5-5');
    });

    it('tells the page when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(events).toEqual(['signedOut']);
      expect(has('form')).toBe(false);
    });

    it('says what the section is for and what a check sends', async () => {
      await setup();

      expect(text()).toContain('your own AI account');
      expect(text()).toContain('stored encrypted and never shown again');
      expect(text()).toContain('one short test message and nothing about your training');
    });
  });

  describe('nothing set up yet', () => {
    beforeEach(() => setup());

    it('says so and shows no status, check or remove', () => {
      expect(testId('none')).toBe('No AI provider set up yet.');
      expect(has('[data-testid="status"]')).toBe(false);
      expect(() => button('Check connection')).toThrow();
      expect(() => button('Remove')).toThrow();
    });

    it('starts the form with Anthropic and an empty model', () => {
      expect(value('#ai-provider')).toBe('anthropic');
      expect(value('#ai-model')).toBe('');
      expect(value('#ai-key')).toBe('');
      expect(query(panel, 'button[type="submit"]').textContent?.trim()).toBe('Save');
    });

    it('offers only Anthropic when the operator allows no address', () => {
      expect(optionTexts('#ai-provider')).toEqual(['Anthropic']);
    });

    it('has a key field that is a password field without autofill', () => {
      const field = query<HTMLInputElement>(panel, '#ai-key');

      expect(field.type).toBe('password');
      expect(field.getAttribute('autocomplete')).toBe('off');
      expect(field.getAttribute('spellcheck')).toBe('false');
      expect(query(panel, 'label[for="ai-key"]').textContent?.trim()).toBe('API key');
    });

    it('sends Anthropic with a trimmed key and model and empties the key at once', async () => {
      const pending = deferred<SaveProviderResult>();
      api.save.mockReturnValue(pending.promise);
      await type('#ai-model', '  claude-sonnet-5-5  ');
      await type('#ai-key', `  ${KEY}  `);

      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await fixture.whenStable();
      fixture.detectChanges();

      expect(api.save).toHaveBeenCalledExactlyOnceWith({
        provider: 'anthropic',
        model: 'claude-sonnet-5-5',
        api_key: KEY,
      });
      expect(value('#ai-key')).toBe(''); // gone while the request is still running
      pending.resolve(saved(ANTHROPIC));
      await settle(fixture);
    });

    it('shows the setup after saving and says what to do next', async () => {
      api.save.mockResolvedValue(saved(ANTHROPIC));
      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', KEY);

      await submit();

      expect(testId('provider')).toBe('Anthropic');
      expect(testId('model')).toBe('claude-sonnet-5-5');
      expect(testId('key')).toBe('Stored');
      expect(testId('status')).toBe('Not checked yet');
      expect(text()).toContain('Saved. Press "Check connection" to see that it works.');
      expect(value('#ai-key')).toBe('');
      expect(query(panel, 'button[type="submit"]').textContent?.trim()).toBe('Save changes');
    });

    it('never shows the key anywhere on the page', async () => {
      api.save.mockResolvedValue(saved(ANTHROPIC));
      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', KEY);

      await submit();

      expect(panel.innerHTML).not.toContain(KEY);
      expect(text()).not.toContain(KEY);
      expect(Array.from(panel.querySelectorAll('input')).every((i) => i.value !== KEY)).toBe(true);
    });

    it('empties the key after a refusal too', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['No.'],
        fields: { model: ['No.'] },
      });
      await type('#ai-model', 'x');
      await type('#ai-key', KEY);

      await submit();

      expect(value('#ai-key')).toBe('');
      expect(panel.innerHTML).not.toContain(KEY);
    });

    it('empties the key after a failed request too', async () => {
      api.save.mockRejectedValue(new Error('offline'));
      await type('#ai-model', 'x');
      await type('#ai-key', KEY);

      await submit();

      expect(value('#ai-key')).toBe('');
      expect(panel.innerHTML).not.toContain(KEY);
    });
  });

  describe('input that cannot be used', () => {
    beforeEach(() => setup());

    it('asks for the model and the key and names the fields', async () => {
      await submit();

      expect(alerts()).toEqual(['Enter the name of the model.', 'Enter your API key.']);
      expect(query(panel, '#ai-model').getAttribute('aria-invalid')).toBe('true');
      expect(query(panel, '#ai-key').getAttribute('aria-invalid')).toBe('true');
      expect(api.save).not.toHaveBeenCalled();
    });

    it.each(['-gpt', '.x', 'a b', 'a;b', 'model<script>', 'é', 'm'.repeat(101)])(
      'refuses "%s" as a model',
      async (model) => {
        await type('#ai-model', model);
        await type('#ai-key', KEY);

        await submit();

        expect(alerts()).toHaveLength(1);
        expect(alerts()[0]).toContain('letters, digits');
        expect(api.save).not.toHaveBeenCalled();
      },
    );

    it.each(['claude-sonnet-5-5', 'llama3.1:8b', 'org/model_v2.1', 'm'.repeat(100)])(
      'takes "%s" as a model',
      async (model) => {
        api.save.mockResolvedValue(saved(ANTHROPIC));
        await type('#ai-model', model);
        await type('#ai-key', KEY);

        await submit();

        expect(api.save).toHaveBeenCalledTimes(1);
      },
    );

    it.each(['has space', 'ünï', 'k'.repeat(501), 'tab\there'])(
      'refuses "%s" as a key',
      async (key) => {
        await type('#ai-model', 'claude-sonnet-5-5');
        await type('#ai-key', key);

        await submit();

        expect(alerts()).toEqual([
          'A key has no spaces or special characters and at most 500 characters.',
        ]);
        expect(api.save).not.toHaveBeenCalled();
      },
    );

    it('takes a key of 500 characters', async () => {
      api.save.mockResolvedValue(saved(ANTHROPIC));
      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', 'k'.repeat(500));

      await submit();

      expect(api.save).toHaveBeenCalledTimes(1);
    });

    it('clears the messages once everything is right', async () => {
      await submit();
      expect(alerts()).toHaveLength(2);
      api.save.mockResolvedValue(saved(ANTHROPIC));

      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', KEY);
      await submit();

      expect(alerts()).toEqual([]);
    });
  });

  describe('what the server says about a save', () => {
    beforeEach(async () => {
      await setup();
      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', KEY);
    });

    it.each([
      ['provider', '#ai-provider'],
      ['model', '#ai-model'],
      ['api_key', '#ai-key'],
    ])('places a message for "%s" at its field', async (field, selector) => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Nope.'],
        fields: { [field]: ['Nope.'] },
      });

      await submit();

      expect(alerts()).toEqual(['Nope.']);
      const next = query(panel, selector).parentElement?.querySelector('.field-error');
      expect(next?.textContent).toBe('Nope.');
    });

    it('shows anything else at the top, once', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['Something odd.'],
        fields: { non_field_errors: ['Something odd.'] },
      });

      await submit();

      expect(alerts()).toEqual(['Something odd.']);
    });

    it('shows a refusal without fields as it is', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['The input was not accepted.'],
        fields: {},
      });

      await submit();

      expect(alerts()).toEqual(['The input was not accepted.']);
    });

    it('joins several messages for one field', async () => {
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['A.', 'B.'],
        fields: { model: ['A.', 'B.'] },
      });

      await submit();

      expect(alerts()).toEqual(['A. B.']);
    });

    it('keeps what the user typed, except the key', async () => {
      api.save.mockResolvedValue({ kind: 'invalid', errors: ['No.'], fields: { model: ['No.'] } });

      await submit();

      expect(value('#ai-model')).toBe('claude-sonnet-5-5');
    });

    it('tells the page when the session ended', async () => {
      api.save.mockResolvedValue({ kind: 'forbidden' });

      await submit();

      expect(events).toEqual(['signedOut']);
    });

    it('says so when saving does not work', async () => {
      api.save.mockRejectedValue(new Error('offline'));

      await submit();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('sends only once when submitted twice in a row, and shows that it is working', async () => {
      const pending = deferred<SaveProviderResult>();
      api.save.mockReturnValue(pending.promise);

      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      await fixture.whenStable();
      fixture.detectChanges();
      const submitButton = query<HTMLButtonElement>(panel, 'button[type="submit"]');
      expect(submitButton.disabled).toBe(true);
      expect(submitButton.textContent).toContain('Working');
      pending.resolve(saved(ANTHROPIC));
      await settle(fixture);

      expect(api.save).toHaveBeenCalledTimes(1);
      expect(submitButton.disabled).toBe(false);
    });

    it('does not let the browser submit the page', async () => {
      const event = new Event('submit', { cancelable: true });
      query<HTMLFormElement>(panel, 'form').dispatchEvent(event);
      await settle(fixture);

      expect(event.defaultPrevented).toBe(true);
    });
  });

  describe('a setup that exists', () => {
    beforeEach(() => setup(ok(CONNECTED)));

    it('shows provider, model, key, status, times and usage', () => {
      expect(testId('provider')).toBe('Anthropic');
      expect(testId('model')).toBe('claude-sonnet-5-5');
      expect(testId('key')).toBe('Stored');
      expect(testId('status')).toBe('Connected');
      // the day is the one of the machine's time zone, worked out independently of the page
      expect(testId('checked')).toContain(dayOf(CONNECTED.last_checked_at as string));
      expect(testId('success')).toContain(dayOf(CONNECTED.last_success_at as string));
      expect(testId('usage')).toBe('1,234 calls, 9,000 input and 1 output tokens');
      expect(text()).toContain('Last 30 days');
    });

    it('says "1 call" for a single call', async () => {
      await setup(ok({ ...CONNECTED, usage: { ...CONNECTED.usage, calls: 1 } }));

      expect(testId('usage')).toContain('1 call,');
    });

    it('says "Never" while nothing was checked', async () => {
      await setup(ok(ANTHROPIC));

      expect(testId('checked')).toBe('Never');
      expect(testId('success')).toBe('Never');
    });

    it.each([
      ['untested', 'Not checked yet'],
      ['connected', 'Connected'],
      ['invalid', 'The provider did not accept the key at the last check'],
      ['unavailable', 'The provider could not be reached at the last check'],
    ] as const)('explains the status %s', async (status, expected) => {
      await setup(ok({ ...CONNECTED, status }));

      expect(testId('status')).toBe(expected);
    });

    it('starts the form from the saved setup, with an empty key field', () => {
      expect(value('#ai-provider')).toBe('anthropic');
      expect(value('#ai-model')).toBe('claude-sonnet-5-5');
      expect(value('#ai-key')).toBe('');
      expect(query(panel, 'label[for="ai-key"]').textContent?.trim()).toBe('Replace the API key');
      expect(text()).toContain('A key is stored. Leave this empty to keep it.');
    });

    it('does not show the address row for Anthropic', () => {
      expect(has('[data-testid="address"]')).toBe(false);
    });

    it('shows the model and the usage as text, never as markup', async () => {
      await setup(ok({ ...CONNECTED, model: '<img src=x onerror=alert(1)>' }));

      expect(testId('model')).toBe('<img src=x onerror=alert(1)>');
      expect(panel.querySelector('img')).toBeNull();
    });

    it('keeps the stored key when only the model changes', async () => {
      api.save.mockResolvedValue(saved({ ...ANTHROPIC, model: 'claude-opus-5-5' }));
      await type('#ai-model', 'claude-opus-5-5');

      await submit();

      expect(api.save).toHaveBeenCalledExactlyOnceWith({
        provider: 'anthropic',
        model: 'claude-opus-5-5',
      });
      expect(Object.keys(api.save.mock.calls[0][0])).not.toContain('api_key');
    });

    it('sends a new key to replace the stored one', async () => {
      api.save.mockResolvedValue(saved(ANTHROPIC));
      await type('#ai-key', OTHER_KEY);

      await submit();

      expect(api.save.mock.calls[0][0]).toEqual({
        provider: 'anthropic',
        model: 'claude-sonnet-5-5',
        api_key: OTHER_KEY,
      });
    });

    it('shows the saved status again after a save that changed nothing', async () => {
      api.save.mockResolvedValue(saved(CONNECTED));

      await submit();

      expect(testId('status')).toBe('Connected');
    });
  });

  describe('checking', () => {
    beforeEach(() => setup(ok(ANTHROPIC)));

    it('says that the connection works and shows the new status', async () => {
      api.check.mockResolvedValue({
        kind: 'checked',
        state: CONNECTED,
        check: { ok: true, problem: null, message: '', retry_after: null },
      });

      await click('Check connection');

      expect(text()).toContain('The connection works.');
      expect(testId('status')).toBe('Connected');
      expect(api.check).toHaveBeenCalledTimes(1);
    });

    it('shows the text of the server for a problem and the new status', async () => {
      api.check.mockResolvedValue({
        kind: 'checked',
        state: { ...ANTHROPIC, status: 'invalid' },
        check: {
          ok: false,
          problem: 'invalid_key',
          message: 'The provider did not accept the key. Check that you copied all of it.',
          retry_after: null,
        },
      });

      await click('Check connection');

      expect(alerts()).toEqual([
        'The provider did not accept the key. Check that you copied all of it.',
      ]);
      expect(testId('status')).toBe('The provider did not accept the key at the last check');
    });

    it('adds how long the provider asked to wait', async () => {
      api.check.mockResolvedValue({
        kind: 'checked',
        state: ANTHROPIC,
        check: {
          ok: false,
          problem: 'rate_limited',
          message: 'The provider is asking to slow down. Please try again in a moment.',
          retry_after: 30,
        },
      });

      await click('Check connection');

      expect(alerts()).toEqual([
        'The provider is asking to slow down. Please try again in a moment. Try again in 30 seconds.',
      ]);
    });

    it('adds no wait of zero seconds', async () => {
      api.check.mockResolvedValue({
        kind: 'checked',
        state: ANTHROPIC,
        check: { ok: false, problem: 'rate_limited', message: 'Slow down.', retry_after: 0 },
      });

      await click('Check connection');

      expect(alerts()).toEqual(['Slow down.']);
    });

    it('explains when there were too many checks', async () => {
      api.check.mockResolvedValue({ kind: 'rate_limited' });

      await click('Check connection');

      expect(alerts()).toEqual(['Too many checks. Please wait a minute and try again.']);
    });

    it('says when the setup is gone and shows the empty state', async () => {
      api.check.mockResolvedValue({ kind: 'not_configured' });
      api.get.mockResolvedValue(ok(NOT_SET_UP));

      await click('Check connection');

      expect(alerts()).toEqual(['There is no AI provider set up any more.']);
      expect(testId('none')).toBe('No AI provider set up yet.');
    });

    it('tells the page when the session ended', async () => {
      api.check.mockResolvedValue({ kind: 'forbidden' });

      await click('Check connection');

      expect(events).toEqual(['signedOut']);
    });

    it('says so when the check does not work', async () => {
      api.check.mockRejectedValue(new Error('offline'));

      await click('Check connection');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('runs only once when clicked twice in a row, and disables the buttons meanwhile', async () => {
      const pending = deferred<CheckProviderResult>();
      api.check.mockReturnValue(pending.promise);

      const target = button('Check connection');
      target.click();
      target.click();
      fixture.detectChanges();
      expect(button('Check connection').disabled).toBe(true);
      expect(button('Remove').disabled).toBe(true);
      pending.resolve({ kind: 'rate_limited' });
      await settle(fixture);

      expect(api.check).toHaveBeenCalledTimes(1);
      expect(button('Check connection').disabled).toBe(false);
    });

    it('clears an earlier message with the next check', async () => {
      api.check.mockResolvedValueOnce({ kind: 'rate_limited' });
      await click('Check connection');
      expect(alerts()).toHaveLength(1);
      api.check.mockResolvedValueOnce({
        kind: 'checked',
        state: CONNECTED,
        check: { ok: true, problem: null, message: '', retry_after: null },
      });

      await click('Check connection');

      expect(alerts()).toEqual([]);
    });

    it('says that unsaved changes are not part of the check', async () => {
      expect(has('[data-testid="unsaved"]')).toBe(false);

      await type('#ai-model', 'claude-opus-5-5');

      expect(testId('unsaved')).toBe(
        'You have changes that are not saved. The check uses the saved setup.',
      );
    });

    it.each([
      ['a new key', '#ai-key', KEY],
      ['another model', '#ai-model', 'other-model'],
    ])('treats %s as unsaved', async (_name, selector, input) => {
      await type(selector, input);

      expect(has('[data-testid="unsaved"]')).toBe(true);
    });

    it('does not call a model with spaces around it a change', async () => {
      await type('#ai-model', '  claude-sonnet-5-5 ');

      expect(has('[data-testid="unsaved"]')).toBe(false);
    });
  });

  describe('removing', () => {
    beforeEach(() => setup(ok(CONNECTED)));

    it('asks first and removes nothing until confirmed', async () => {
      await click('Remove');

      expect(text()).toContain('Remove the AI provider?');
      expect(text()).toContain('The stored key is deleted from PaceForge.');
      expect(api.remove).not.toHaveBeenCalled();
    });

    it('does nothing when cancelled', async () => {
      await click('Remove');

      await click('Cancel');

      expect(api.remove).not.toHaveBeenCalled();
      expect(text()).not.toContain('Remove the AI provider?');
      expect(button('Check connection')).toBeTruthy();
    });

    it('removes the setup, says so and shows the empty state', async () => {
      api.remove.mockResolvedValue({ kind: 'removed' });
      api.get.mockResolvedValue(ok(NOT_SET_UP));
      await click('Remove');

      await click('Yes, remove');

      expect(api.remove).toHaveBeenCalledTimes(1);
      expect(text()).toContain('The AI provider was removed and the stored key deleted.');
      expect(testId('none')).toBe('No AI provider set up yet.');
      expect(value('#ai-model')).toBe('');
      expect(value('#ai-provider')).toBe('anthropic');
    });

    it('tells the page when the session ended', async () => {
      api.remove.mockResolvedValue({ kind: 'forbidden' });
      await click('Remove');

      await click('Yes, remove');

      expect(events).toEqual(['signedOut']);
    });

    it('says so when removing does not work and keeps the setup', async () => {
      api.remove.mockRejectedValue(new Error('offline'));
      await click('Remove');

      await click('Yes, remove');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(testId('model')).toBe('claude-sonnet-5-5');
    });

    it('says so when the setup cannot be refreshed after removing', async () => {
      api.remove.mockResolvedValue({ kind: 'removed' });
      api.get.mockRejectedValue(new Error('offline'));
      await click('Remove');

      await click('Yes, remove');

      expect(alerts()).toEqual(['The setup could not be refreshed. Please try again.']);
      expect(text()).toContain('The AI provider was removed');
    });

    it('tells the page when the refresh finds the session gone', async () => {
      api.remove.mockResolvedValue({ kind: 'removed' });
      api.get.mockResolvedValue({ kind: 'forbidden' });
      await click('Remove');

      await click('Yes, remove');

      expect(events).toEqual(['signedOut']);
    });

    it('removes only once when confirmed twice in a row', async () => {
      const pending = deferred<RemoveProviderResult>();
      api.remove.mockReturnValue(pending.promise);
      await click('Remove');

      const confirm = button('Yes, remove');
      confirm.click();
      confirm.click();
      pending.resolve({ kind: 'removed' });
      await settle(fixture);

      expect(api.remove).toHaveBeenCalledTimes(1);
    });

    it('clears an earlier message when it asks', async () => {
      api.check.mockResolvedValue({ kind: 'rate_limited' });
      await click('Check connection');
      expect(alerts()).toHaveLength(1);

      await click('Remove');

      expect(alerts()).toEqual([]);
    });
  });

  describe('OpenAI-compatible endpoints', () => {
    it('are offered when the operator allows an address', async () => {
      await setup(ok({ ...NOT_SET_UP, allowed_base_urls: [LOCAL, OPENAI] }));

      expect(optionTexts('#ai-provider')).toEqual([
        'Anthropic',
        'OpenAI-compatible (OpenAI, Ollama, llama.cpp …)',
      ]);
    });

    it('stay visible for a user who has one even if the list is empty now', async () => {
      await setup(ok({ ...COMPATIBLE, allowed_base_urls: [] }));

      expect(optionTexts('#ai-provider')).toHaveLength(2);
    });

    it('show the address choice only for them, with the allowed addresses', async () => {
      await setup(ok({ ...NOT_SET_UP, allowed_base_urls: [LOCAL, OPENAI] }));
      expect(has('#ai-base-url')).toBe(false);

      await choose('#ai-provider', 'openai_compatible');

      expect(optionTexts('#ai-base-url')).toEqual([LOCAL, OPENAI]);
      expect(value('#ai-base-url')).toBe(LOCAL);
      expect(text()).toContain('Only addresses that the operator of this server has allowed');
    });

    it('send provider, model and the chosen address, without a key when none is typed', async () => {
      await setup(ok({ ...NOT_SET_UP, allowed_base_urls: [LOCAL, OPENAI] }));
      api.save.mockResolvedValue(saved(COMPATIBLE));
      await choose('#ai-provider', 'openai_compatible');
      await choose('#ai-base-url', OPENAI);
      await type('#ai-model', 'gpt-4o');

      await submit();

      expect(api.save).toHaveBeenCalledExactlyOnceWith({
        provider: 'openai_compatible',
        model: 'gpt-4o',
        base_url: OPENAI,
      });
    });

    it('may send a key, which is optional', async () => {
      await setup(ok({ ...NOT_SET_UP, allowed_base_urls: [LOCAL] }));
      api.save.mockResolvedValue(saved(COMPATIBLE));
      await choose('#ai-provider', 'openai_compatible');
      await type('#ai-model', 'llama3.1:8b');
      await type('#ai-key', KEY);

      await submit();

      expect(api.save.mock.calls[0][0]).toEqual({
        provider: 'openai_compatible',
        model: 'llama3.1:8b',
        base_url: LOCAL,
        api_key: KEY,
      });
      expect(query(panel, 'label[for="ai-key"]').textContent?.trim()).toBe('API key (optional)');
    });

    it('does not send an address for Anthropic after switching back', async () => {
      await setup(ok({ ...NOT_SET_UP, allowed_base_urls: [LOCAL] }));
      api.save.mockResolvedValue(saved(ANTHROPIC));
      await choose('#ai-provider', 'openai_compatible');
      await choose('#ai-provider', 'anthropic');
      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', KEY);

      await submit();

      expect(Object.keys(api.save.mock.calls[0][0]).sort()).toEqual(
        ['api_key', 'model', 'provider'].sort(),
      );
    });

    it('show the saved setup with its address and no key', async () => {
      await setup(ok(COMPATIBLE));

      expect(testId('provider')).toBe('OpenAI-compatible (OpenAI, Ollama, llama.cpp …)');
      expect(testId('address')).toBe(LOCAL);
      expect(testId('key')).toBe('None');
      expect(value('#ai-base-url')).toBe(LOCAL);
    });

    it('mark an address that is not allowed any more', async () => {
      await setup(ok({ ...COMPATIBLE, allowed_base_urls: [OPENAI] }));

      expect(optionTexts('#ai-base-url')).toEqual([OPENAI, `${LOCAL} (not allowed any more)`]);
      expect(value('#ai-base-url')).toBe(LOCAL);
    });

    it('place the message about the address at it', async () => {
      await setup(ok({ ...NOT_SET_UP, allowed_base_urls: [LOCAL] }));
      api.save.mockResolvedValue({
        kind: 'invalid',
        errors: ['This address is not allowed on this server.'],
        fields: { base_url: ['This address is not allowed on this server.'] },
      });
      await choose('#ai-provider', 'openai_compatible');
      await type('#ai-model', 'llama3.1:8b');

      await submit();

      expect(alerts()).toEqual(['This address is not allowed on this server.']);
      expect(query(panel, '#ai-base-url').getAttribute('aria-invalid')).toBe('true');
    });

    it('asks for an address when there is none to choose', async () => {
      await setup(ok({ ...COMPATIBLE, allowed_base_urls: [], base_url: null }));
      await type('#ai-model', 'llama3.1:8b');

      await submit();

      expect(alerts()).toEqual(['Choose the address of the endpoint.']);
      expect(api.save).not.toHaveBeenCalled();
    });
  });

  describe('the stored key and where it may go', () => {
    it('is not kept when the provider changes, and the hint says so', async () => {
      await setup(ok({ ...CONNECTED, allowed_base_urls: [LOCAL] }));

      await choose('#ai-provider', 'openai_compatible');

      expect(text()).toContain('The stored key is not used for another provider or address.');
      expect(text()).not.toContain('Leave this empty to keep it.');
    });

    it('is not kept when the address changes', async () => {
      await setup(ok({ ...COMPATIBLE, has_key: true }));
      expect(text()).toContain('A key is stored. Leave this empty to keep it.');

      await choose('#ai-base-url', OPENAI);

      expect(text()).toContain('The stored key is not used for another provider or address.');
    });

    it('is kept again when the choice is changed back', async () => {
      await setup(ok({ ...CONNECTED, allowed_base_urls: [LOCAL] }));
      await choose('#ai-provider', 'openai_compatible');

      await choose('#ai-provider', 'anthropic');

      expect(text()).toContain('A key is stored. Leave this empty to keep it.');
    });

    it('asks for a key when going from a compatible endpoint to Anthropic', async () => {
      await setup(ok({ ...COMPATIBLE, has_key: true }));
      await choose('#ai-provider', 'anthropic');
      await type('#ai-model', 'claude-sonnet-5-5');

      await submit();

      expect(alerts()).toEqual(['Enter your API key.']);
      expect(api.save).not.toHaveBeenCalled();
    });

    it('is removable for a compatible endpoint with a checkbox, which sends an empty key', async () => {
      await setup(ok({ ...COMPATIBLE, has_key: true }));
      api.save.mockResolvedValue(saved(COMPATIBLE));
      expect(has('#ai-remove-key')).toBe(true);

      const box = query<HTMLInputElement>(panel, '#ai-remove-key');
      box.checked = true;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);
      expect(query<HTMLInputElement>(panel, '#ai-key').disabled).toBe(true);
      await submit();

      expect(api.save.mock.calls[0][0]).toEqual({
        provider: 'openai_compatible',
        model: 'llama3.1:8b',
        base_url: LOCAL,
        api_key: '',
      });
    });

    it('clears a typed key when the checkbox is ticked, and unticking lets the user type again', async () => {
      await setup(ok({ ...COMPATIBLE, has_key: true }));
      await type('#ai-key', KEY);
      const box = query<HTMLInputElement>(panel, '#ai-remove-key');

      box.checked = true;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);
      expect(value('#ai-key')).toBe('');

      box.checked = false;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);
      expect(query<HTMLInputElement>(panel, '#ai-key').disabled).toBe(false);
    });

    it('offers no checkbox for Anthropic, without a stored key or after a change of address', async () => {
      await setup(ok(CONNECTED));
      expect(has('#ai-remove-key')).toBe(false);

      await setup(ok(COMPATIBLE));
      expect(has('#ai-remove-key')).toBe(false);

      await setup(ok({ ...COMPATIBLE, has_key: true }));
      await choose('#ai-base-url', OPENAI);
      expect(has('#ai-remove-key')).toBe(false);
    });

    it('does not send an empty key when the checkbox was ticked and the provider then changed', async () => {
      await setup(ok({ ...COMPATIBLE, has_key: true }));
      api.save.mockResolvedValue(saved(ANTHROPIC));
      const box = query<HTMLInputElement>(panel, '#ai-remove-key');
      box.checked = true;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);
      await choose('#ai-provider', 'anthropic');
      expect(query<HTMLInputElement>(panel, '#ai-key').disabled).toBe(false);
      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', KEY);

      await submit();

      expect(api.save.mock.calls[0][0]).toEqual({
        provider: 'anthropic',
        model: 'claude-sonnet-5-5',
        api_key: KEY,
      });
    });
  });

  describe('details that are easy to get wrong', () => {
    it('submits once even when the second submit comes while the first is running', async () => {
      await setup(ok(CONNECTED));
      const pending = deferred<SaveProviderResult>();
      api.save.mockReturnValue(pending.promise);
      await type('#ai-model', 'claude-opus-5-5');

      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      query<HTMLFormElement>(panel, 'form').dispatchEvent(
        new Event('submit', { cancelable: true }),
      );
      pending.resolve(saved(ANTHROPIC));
      await settle(fixture);

      expect(api.save).toHaveBeenCalledTimes(1);
    });

    it('does not show the removal question again when a setup is saved after a removal', async () => {
      await setup(ok(CONNECTED));
      api.remove.mockResolvedValue({ kind: 'removed' });
      api.get.mockResolvedValue(ok(NOT_SET_UP));
      await click('Remove');
      await click('Yes, remove');
      api.save.mockResolvedValue(saved(ANTHROPIC));
      await type('#ai-model', 'claude-sonnet-5-5');
      await type('#ai-key', KEY);

      await submit();

      expect(text()).not.toContain('Remove the AI provider?');
      expect(button('Check connection')).toBeTruthy();
    });

    it('does not keep a typed key on the page after the setup was removed', async () => {
      await setup(ok(CONNECTED));
      api.remove.mockResolvedValue({ kind: 'removed' });
      api.get.mockResolvedValue(ok(NOT_SET_UP));
      await type('#ai-key', KEY);
      await click('Remove');

      await click('Yes, remove');

      expect(value('#ai-key')).toBe('');
      expect(panel.innerHTML).not.toContain(KEY);
    });

    it('unticks "Remove the stored key" after a refusal, like the key field is emptied', async () => {
      await setup(ok({ ...COMPATIBLE, has_key: true }));
      api.save.mockResolvedValue({ kind: 'invalid', errors: ['No.'], fields: { model: ['No.'] } });
      const box = query<HTMLInputElement>(panel, '#ai-remove-key');
      box.checked = true;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);

      await submit();

      expect(query<HTMLInputElement>(panel, '#ai-key').disabled).toBe(false);
      expect(query<HTMLInputElement>(panel, '#ai-remove-key').checked).toBe(false);
    });

    it('chooses the first allowed address when switching to a compatible endpoint', async () => {
      await setup(ok({ ...NOT_SET_UP, allowed_base_urls: [LOCAL, OPENAI] }));
      api.save.mockResolvedValue(saved(COMPATIBLE));
      await choose('#ai-provider', 'openai_compatible');
      await type('#ai-model', 'llama3.1:8b');

      await submit();

      expect(api.save.mock.calls[0][0].base_url).toBe(LOCAL);
    });

    it('keeps the saved address when switching away and back', async () => {
      await setup(
        ok({ ...COMPATIBLE, base_url: OPENAI, has_key: true, allowed_base_urls: [LOCAL, OPENAI] }),
      );

      await choose('#ai-provider', 'anthropic');
      await choose('#ai-provider', 'openai_compatible');

      expect(value('#ai-base-url')).toBe(OPENAI);
      expect(text()).toContain('A key is stored. Leave this empty to keep it.');
    });

    it('shows the saved provider as the chosen one', async () => {
      await setup(ok(COMPATIBLE));

      expect(value('#ai-provider')).toBe('openai_compatible');
    });

    it('calls a changed provider alone an unsaved change', async () => {
      await setup(ok(COMPATIBLE));

      await choose('#ai-provider', 'anthropic');

      expect(has('[data-testid="unsaved"]')).toBe(true);
    });

    it('calls a changed address alone an unsaved change', async () => {
      await setup(ok(COMPATIBLE));
      expect(has('[data-testid="unsaved"]')).toBe(false);

      await choose('#ai-base-url', OPENAI);

      expect(has('[data-testid="unsaved"]')).toBe(true);
    });

    it('calls ticking "Remove the stored key" alone an unsaved change', async () => {
      await setup(ok({ ...COMPATIBLE, has_key: true }));
      const box = query<HTMLInputElement>(panel, '#ai-remove-key');

      box.checked = true;
      box.dispatchEvent(new Event('change'));
      await settle(fixture);

      expect(has('[data-testid="unsaved"]')).toBe(true);
    });
  });
});
