import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CoachApi } from '../../core/coach/coach-api';
import { AiProviderState, GetProviderResult } from '../../core/coach/coach-models';
import { IntervalsConnectionApi } from '../../core/integrations/intervals-api';
import {
  CheckConnectionResult,
  ConnectResult,
  DisconnectResult,
  GetConnectionResult,
  IntervalsConnection,
} from '../../core/integrations/intervals-models';
import { query, required, settle, typeInto } from '../../testing/dom';
import { ConnectionsPage } from './connections-page';

const KEY = 'k3y-0123456789-abcdefghij';

const CONNECTION: IntervalsConnection = {
  status: 'connected',
  athlete_id: 'i555',
  connected_at: '2026-11-12T11:55:00Z',
  last_checked_at: '2026-11-12T12:00:00Z',
};
const INVALID: IntervalsConnection = { ...CONNECTION, status: 'invalid' };

// The AI provider has a panel of its own, tested in ai-provider-panel.spec.ts.
const NO_AI: AiProviderState = {
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

function createApiStub() {
  return {
    get: vi.fn<() => Promise<GetConnectionResult>>(),
    connect: vi.fn<(apiKey: string) => Promise<ConnectResult>>(),
    check: vi.fn<() => Promise<CheckConnectionResult>>(),
    disconnect: vi.fn<() => Promise<DisconnectResult>>(),
  };
}

describe('ConnectionsPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let coach: { get: ReturnType<typeof vi.fn<() => Promise<GetProviderResult>>> };
  let fixture: ComponentFixture<ConnectionsPage>;
  let page: HTMLElement;

  async function setup(
    first: GetConnectionResult = { kind: 'not_connected' },
    ai: GetProviderResult = { kind: 'ok', state: NO_AI },
  ) {
    api = createApiStub();
    api.get.mockResolvedValue(first);
    coach = { get: vi.fn<() => Promise<GetProviderResult>>().mockResolvedValue(ai) };
    TestBed.configureTestingModule({
      imports: [ConnectionsPage],
      providers: [
        provideRouter([]),
        { provide: IntervalsConnectionApi, useValue: api },
        { provide: CoachApi, useValue: coach },
      ],
    });
    fixture = TestBed.createComponent(ConnectionsPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const connected = (connection = CONNECTION): GetConnectionResult => ({
    kind: 'connected',
    connection,
  });
  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const field = () => query<HTMLInputElement>(page, '#api-key');
  const testId = (id: string) => query(page, `[data-testid="${id}"]`).textContent?.trim();

  function button(label: string): HTMLButtonElement {
    const match = Array.from(page.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').trim().includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(label: string): Promise<void> {
    button(label).click();
    await settle(fixture);
  }

  async function submitKey(value = KEY): Promise<void> {
    typeInto(page, '#api-key', value);
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the state arrives', () => {
      api = createApiStub();
      api.get.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [ConnectionsPage],
        providers: [
          provideRouter([]),
          { provide: IntervalsConnectionApi, useValue: api },
          { provide: CoachApi, useValue: { get: () => new Promise<never>(() => undefined) } },
        ],
      });
      fixture = TestBed.createComponent(ConnectionsPage);
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain('Loading');
      expect(fixture.nativeElement.querySelector('form')).toBeNull();
    });

    it('offers the form and no status when there is no connection', async () => {
      await setup();

      expect(text()).toContain('Not connected.');
      expect(page.querySelector('[data-testid="status"]')).toBeNull();
      expect(button('Connect')).toBeDefined();
      expect(page.textContent).not.toContain('Check connection');
    });

    it('shows the connection with athlete, status and the time of the last check', async () => {
      await setup(connected());

      expect(testId('status')).toBe('Connected');
      expect(testId('athlete')).toBe('i555');
      expect(testId('checked')).toContain('Nov 12, 2026');
      expect(button('Check connection')).toBeDefined();
      expect(button('Disconnect')).toBeDefined();
      expect(button('Save new key')).toBeDefined();
    });

    it('points out an invalid connection', async () => {
      await setup(connected(INVALID));

      expect(testId('status')).toContain('Needs attention');
    });

    it('offers to try again when the state cannot be loaded, and then shows it', async () => {
      await setup();
      api.get.mockRejectedValueOnce(new Error('offline'));
      api.get.mockResolvedValueOnce(connected());
      fixture = TestBed.createComponent(ConnectionsPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your connections could not be loaded.']);
      expect(page.querySelector('form')).toBeNull();

      await click('Try again');

      expect(alerts()).toEqual([]);
      expect(testId('athlete')).toBe('i555');
    });

    it('sends a user whose session is gone to the sign-in page', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/login');
      expect(page.querySelector('form')).toBeNull();
    });
  });

  describe('the AI provider', () => {
    it('has its section below the Intervals.icu one, loaded once', async () => {
      await setup();

      const section = query(page, 'app-ai-provider-panel');
      expect(section.textContent).toContain('AI coach');
      expect(
        query(page, 'form').compareDocumentPosition(section) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(coach.get).toHaveBeenCalledTimes(1);
    });

    it('is not shown while the Intervals.icu state cannot be loaded', async () => {
      api = createApiStub();
      api.get.mockRejectedValue(new Error('offline'));
      TestBed.configureTestingModule({
        imports: [ConnectionsPage],
        providers: [
          provideRouter([]),
          { provide: IntervalsConnectionApi, useValue: api },
          { provide: CoachApi, useValue: { get: vi.fn() } },
        ],
      });
      fixture = TestBed.createComponent(ConnectionsPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);

      expect(page.querySelector('app-ai-provider-panel')).toBeNull();
    });

    it('ends the session of the page when the panel finds it gone', async () => {
      await setup({ kind: 'not_connected' }, { kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('app-ai-provider-panel')).toBeNull();
      expect(page.querySelector('form')).toBeNull();
    });
  });

  describe('the key field', () => {
    it('is a password field that does not invite autofill or checking', async () => {
      await setup();

      const input = field();
      expect(input.type).toBe('password');
      expect(input.getAttribute('autocomplete')).toBe('off');
      expect(input.getAttribute('spellcheck')).toBe('false');
      expect(input.value).toBe('');
    });

    it('has a label and a hint that says where the key comes from', async () => {
      await setup();

      expect(query(page, 'label[for="api-key"]').textContent).toContain('API key');
      expect(query(page, '#api-key-hint').textContent).toContain('Developer Settings');
      expect(field().getAttribute('aria-describedby')).toBe('api-key-hint');
    });

    it('is called "Replace the API key" while a connection exists', async () => {
      await setup(connected());

      expect(query(page, 'label[for="api-key"]').textContent).toContain('Replace the API key');
    });
  });

  describe('connecting', () => {
    it.each(['', '   ', '\n\t'])('does not send the blank key %j', async (value) => {
      await setup();

      await submitKey(value);

      expect(api.connect).not.toHaveBeenCalled();
      expect(text()).toContain('Enter your API key.');
      expect(field().getAttribute('aria-invalid')).toBe('true');
    });

    it('sends the trimmed key', async () => {
      await setup();
      api.connect.mockResolvedValue({ kind: 'connected', connection: CONNECTION });

      await submitKey(`  ${KEY} \n`);

      expect(api.connect).toHaveBeenCalledExactlyOnceWith(KEY);
    });

    it('shows the connection and says so after a success', async () => {
      await setup();
      api.connect.mockResolvedValue({ kind: 'connected', connection: CONNECTION });

      await submitKey();

      expect(testId('athlete')).toBe('i555');
      expect(testId('status')).toBe('Connected');
      expect(text()).toContain('Connected to Intervals.icu (athlete i555).');
    });

    it('replaces an existing connection', async () => {
      await setup(connected(INVALID));
      api.connect.mockResolvedValue({
        kind: 'connected',
        connection: { ...CONNECTION, athlete_id: 'i777' },
      });

      await submitKey();

      expect(testId('athlete')).toBe('i777');
      expect(testId('status')).toBe('Connected');
    });

    it('shows what Intervals.icu said about a key that is not accepted and keeps the old connection', async () => {
      await setup(connected());
      api.connect.mockResolvedValue({
        kind: 'invalid_key',
        errors: ['Intervals.icu did not accept this API key. Check that you copied all of it.'],
      });

      await submitKey();

      expect(alerts()).toEqual([
        'Intervals.icu did not accept this API key. Check that you copied all of it.',
      ]);
      expect(testId('athlete')).toBe('i555');
    });

    it('explains rate limits', async () => {
      await setup();
      api.connect.mockResolvedValue({ kind: 'rate_limited' });

      await submitKey();

      expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);
    });

    it('shows the message when Intervals.icu cannot be reached', async () => {
      await setup();
      api.connect.mockResolvedValue({ kind: 'unavailable', message: 'Try again later, please.' });

      await submitKey();

      expect(alerts()).toEqual(['Try again later, please.']);
      expect(text()).toContain('Not connected.');
    });

    it('shows a generic message when the request fails', async () => {
      await setup();
      api.connect.mockRejectedValue(new Error('offline'));

      await submitKey();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('sends the user to sign in when the session is gone', async () => {
      await setup();
      api.connect.mockResolvedValue({ kind: 'forbidden' });

      await submitKey();

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });

    it('ignores a second submit while the first is running and disables the button', async () => {
      await setup();
      let finish: (result: ConnectResult) => void = () => undefined;
      api.connect.mockReturnValue(new Promise((resolve) => (finish = resolve)));

      typeInto(page, '#api-key', KEY);
      query(page, 'form').dispatchEvent(new Event('submit'));
      typeInto(page, '#api-key', KEY);
      query(page, 'form').dispatchEvent(new Event('submit'));
      fixture.detectChanges();

      expect(button('Working').disabled).toBe(true);
      expect(api.connect).toHaveBeenCalledTimes(1);
      finish({ kind: 'connected', connection: CONNECTION });
      await settle(fixture);
      expect(button('Save new key').disabled).toBe(false);
    });
  });

  describe('the key never stays on the page', () => {
    const outcomes: [string, () => void][] = [
      [
        'a success',
        () => api.connect.mockResolvedValue({ kind: 'connected', connection: CONNECTION }),
      ],
      [
        'a refused key',
        () => api.connect.mockResolvedValue({ kind: 'invalid_key', errors: ['No.'] }),
      ],
      ['a rate limit', () => api.connect.mockResolvedValue({ kind: 'rate_limited' })],
      [
        'an unavailable service',
        () => api.connect.mockResolvedValue({ kind: 'unavailable', message: 'Later.' }),
      ],
      ['a lost session', () => api.connect.mockResolvedValue({ kind: 'forbidden' })],
      ['a failing request', () => api.connect.mockRejectedValue(new Error('offline'))],
    ];

    it.each(outcomes)('is gone from the field and the page after %s', async (_label, arrange) => {
      await setup();
      arrange();

      await submitKey();

      expect(page.querySelector<HTMLInputElement>('#api-key')?.value ?? '').toBe('');
      expect(page.innerHTML).not.toContain(KEY);
      expect(text()).not.toContain(KEY);
    });

    it('is already gone from the field while the request is still running', async () => {
      await setup();
      api.connect.mockReturnValue(new Promise<never>(() => undefined));

      typeInto(page, '#api-key', KEY);
      query(page, 'form').dispatchEvent(new Event('submit'));
      fixture.detectChanges();

      expect(field().value).toBe('');
      expect(page.innerHTML).not.toContain(KEY);
    });

    it('is not kept as the form value either', async () => {
      await setup();
      api.connect.mockResolvedValue({ kind: 'invalid_key', errors: ['No.'] });

      await submitKey();

      expect(fixture.componentInstance['form'].getRawValue()).toEqual({ apiKey: '' });
    });
  });

  describe('checking', () => {
    it('refreshes the status and says that the key works', async () => {
      await setup(connected());
      api.check.mockResolvedValue({
        kind: 'checked',
        connection: { ...CONNECTION, last_checked_at: '2026-11-13T12:00:00Z' },
      });

      await click('Check connection');

      expect(text()).toContain('The key works.');
      expect(testId('checked')).toContain('Nov 13, 2026');
    });

    it('reports a key that is not accepted any more and offers the way out', async () => {
      await setup(connected());
      api.check.mockResolvedValue({ kind: 'checked', connection: INVALID });

      await click('Check connection');

      expect(alerts()).toEqual([
        'Intervals.icu does not accept the stored key any more. Enter a new key below.',
      ]);
      expect(testId('status')).toContain('Needs attention');
    });

    it('shows that the connection is gone when the server no longer has one', async () => {
      await setup(connected());
      api.check.mockResolvedValue({ kind: 'not_connected' });

      await click('Check connection');

      expect(alerts()).toEqual(['There is no connection any more.']);
      expect(text()).toContain('Not connected.');
    });

    it('explains rate limits and keeps the state', async () => {
      await setup(connected());
      api.check.mockResolvedValue({ kind: 'rate_limited' });

      await click('Check connection');

      expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);
      expect(testId('athlete')).toBe('i555');
    });

    it('shows the message when Intervals.icu cannot be reached and keeps the state', async () => {
      await setup(connected());
      api.check.mockResolvedValue({ kind: 'unavailable', message: 'Try again later, please.' });

      await click('Check connection');

      expect(alerts()).toEqual(['Try again later, please.']);
      expect(testId('status')).toBe('Connected');
    });

    it('shows a generic message when the request fails', async () => {
      await setup(connected());
      api.check.mockRejectedValue(new Error('offline'));

      await click('Check connection');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('sends the user to sign in when the session is gone', async () => {
      await setup(connected());
      api.check.mockResolvedValue({ kind: 'forbidden' });

      await click('Check connection');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });
  });

  describe('disconnecting', () => {
    it('asks first, and nothing happens on cancel', async () => {
      await setup(connected());

      await click('Disconnect');
      expect(text()).toContain('Remove the connection?');
      expect(api.disconnect).not.toHaveBeenCalled();
      await click('Cancel');

      expect(api.disconnect).not.toHaveBeenCalled();
      expect(text()).not.toContain('Remove the connection?');
      expect(testId('athlete')).toBe('i555');
    });

    it('says that the key at Intervals.icu stays valid until a new one is created', async () => {
      await setup(connected());

      await click('Disconnect');

      expect(text()).toContain('create a new one in Intervals.icu');
    });

    it('removes the connection after the confirmation', async () => {
      await setup(connected());
      api.disconnect.mockResolvedValue({ kind: 'disconnected' });

      await click('Disconnect');
      await click('Yes, remove');

      expect(api.disconnect).toHaveBeenCalledTimes(1);
      expect(text()).toContain('Not connected.');
      expect(text()).toContain('The connection was removed and the stored key deleted.');
      expect(page.querySelector('[data-testid="athlete"]')).toBeNull();
    });

    it('shows a generic message when the request fails and keeps the connection', async () => {
      await setup(connected());
      api.disconnect.mockRejectedValue(new Error('offline'));

      await click('Disconnect');
      await click('Yes, remove');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(testId('athlete')).toBe('i555');
    });

    it('sends the user to sign in when the session is gone', async () => {
      await setup(connected());
      api.disconnect.mockResolvedValue({ kind: 'forbidden' });

      await click('Disconnect');
      await click('Yes, remove');

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });
  });
});
