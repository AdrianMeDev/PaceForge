import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CoachApi } from '../../core/coach/coach-api';
import {
  AiCostsState,
  DeletePriceResult,
  GetCostsResult,
  ModelPrice,
  ModelPriceInput,
  MonthlyUsage,
  SavePriceResult,
} from '../../core/coach/coach-models';
import { query, required, settle, typeInto } from '../../testing/dom';
import { AiCostsPanel } from './ai-costs-panel';

const SONNET: ModelPrice = {
  id: 1,
  model: 'claude-sonnet-5-5',
  input_per_million: '3.0000',
  output_per_million: '15.0000',
  cached_per_million: '0.3000',
};
const LOCAL: ModelPrice = {
  id: 2,
  model: 'llama3.1:8b',
  input_per_million: '0.0000',
  output_per_million: '0.0000',
  cached_per_million: null,
};

function month(overrides: Partial<MonthlyUsage> = {}): MonthlyUsage {
  return {
    month: '2026-11',
    calls: 1234,
    input_tokens: 56789,
    output_tokens: 4321,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    cost: '1.2345',
    unpriced_models: [],
    ...overrides,
  };
}

const costs = (state: Partial<AiCostsState> = {}): GetCostsResult => ({
  kind: 'ok',
  state: { prices: [], months: [], ...state },
});

function createApiStub() {
  return {
    getCosts: vi.fn<() => Promise<GetCostsResult>>(),
    savePrice: vi.fn<(input: ModelPriceInput) => Promise<SavePriceResult>>(),
    deletePrice: vi.fn<(id: number) => Promise<DeletePriceResult>>(),
  };
}

describe('AiCostsPanel', () => {
  // jsdom has no modal dialog: this is what the browser does that the question relies on.
  beforeAll(() => {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      if (this.hasAttribute('open')) {
        this.removeAttribute('open');
        this.dispatchEvent(new Event('close'));
      }
    };
  });

  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<AiCostsPanel>;
  let panel: HTMLElement;
  let events: string[];

  async function setup(first: GetCostsResult = costs()) {
    TestBed.resetTestingModule();
    api = createApiStub();
    api.getCosts.mockResolvedValue(first);
    TestBed.configureTestingModule({
      imports: [AiCostsPanel],
      providers: [{ provide: CoachApi, useValue: api }],
    });
    fixture = TestBed.createComponent(AiCostsPanel);
    events = [];
    fixture.componentInstance.signedOut.subscribe(() => events.push('signedOut'));
    panel = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => (panel.textContent ?? '').replace(/\s+/g, ' ');
  const alerts = () =>
    Array.from(panel.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());
  const cell = (id: string) =>
    query(panel, `[data-testid="month-${id}"] [data-testid="cost"]`)
      .textContent?.replace(/\s+/g, ' ')
      .trim();
  const value = (selector: string) => query<HTMLInputElement>(panel, selector).value;

  function button(label: string): HTMLButtonElement {
    const match = Array.from(panel.querySelectorAll('button')).find((b) =>
      ((b.textContent ?? '') + (b.getAttribute('aria-label') ?? '')).includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(label: string): Promise<void> {
    button(label).click();
    await settle(fixture);
  }

  async function submit(fields: {
    model?: string;
    input?: string;
    output?: string;
    cached?: string;
  }) {
    if (fields.model !== undefined) typeInto(panel, '#price-model-name', fields.model);
    if (fields.input !== undefined) typeInto(panel, '#price-input', fields.input);
    if (fields.output !== undefined) typeInto(panel, '#price-output', fields.output);
    if (fields.cached !== undefined) typeInto(panel, '#price-cached', fields.cached);
    await settle(fixture); // the page shows what was typed before the form is sent
    query(panel, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows a loading note until the costs arrive', () => {
      TestBed.resetTestingModule();
      api = createApiStub();
      api.getCosts.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [AiCostsPanel],
        providers: [{ provide: CoachApi, useValue: api }],
      });
      fixture = TestBed.createComponent(AiCostsPanel);
      fixture.detectChanges();

      expect(query(fixture.nativeElement, '[aria-label="Loading"]')).toBeTruthy();
    });

    it('offers a retry when the costs cannot be loaded', async () => {
      await setup();
      api.getCosts.mockRejectedValueOnce(new Error('offline'));
      await (fixture.componentInstance as unknown as { load(): Promise<void> }).load();
      await settle(fixture);
      expect(alerts()).toEqual(['Your AI costs could not be loaded.']);

      await click('Try again');

      expect(alerts()).toEqual([]);
      expect(text()).toContain('Usage per month');
    });

    it('tells the page when the session is gone', async () => {
      await setup({ kind: 'forbidden' });

      expect(events).toEqual(['signedOut']);
    });
  });

  describe('the months', () => {
    it('says so when there are no calls yet', async () => {
      await setup();

      expect(text()).toContain('No AI calls yet.');
      expect(panel.querySelector('table')).toBeNull();
    });

    it('shows calls, tokens and the cost of a fully priced month', async () => {
      await setup(costs({ months: [month()] }));

      const row = query(panel, '[data-testid="month-2026-11"]').textContent ?? '';
      expect(row).toContain('November 2026');
      expect(row).toContain('1,234');
      expect(row).toContain('56,789');
      expect(row).toContain('4,321');
      expect(cell('2026-11')).toBe('$1.2345');
      expect(panel.querySelector('[data-testid="unpriced"]')).toBeNull();
    });

    it('shows a partly priced month as a lower bound with the models without a price', async () => {
      await setup(costs({ months: [month({ cost: '0.5000', unpriced_models: ['gpt-x', 'm2'] })] }));

      expect(cell('2026-11')).toContain('At least $0.50');
      expect(query(panel, '[data-testid="unpriced"]').textContent).toContain('gpt-x, m2');
    });

    it('shows a month without any price as having no cost', async () => {
      await setup(costs({ months: [month({ cost: null, unpriced_models: ['gpt-x'] })] }));

      expect(cell('2026-11')).toContain('No price set');
      expect(cell('2026-11')).not.toContain('$');
      expect(cell('2026-11')).toContain('gpt-x');
    });

    it('shows a free month as zero dollars, not as unpriced', async () => {
      await setup(costs({ months: [month({ cost: '0.0000' })] }));

      expect(cell('2026-11')).toBe('$0.00');
    });

    it('keeps the newest month first, as the server sends them', async () => {
      await setup(costs({ months: [month({ month: '2026-11' }), month({ month: '2026-10' })] }));

      const rows = Array.from(panel.querySelectorAll('tbody tr')).map((r) =>
        r.getAttribute('data-testid'),
      );
      expect(rows).toEqual(['month-2026-11', 'month-2026-10']);
    });

    it('shows model names as plain text', async () => {
      const name = '<img src=x onerror=alert(1)>';
      await setup(
        costs({
          prices: [{ ...SONNET, model: name }],
          months: [month({ cost: null, unpriced_models: [name] })],
        }),
      );

      expect(panel.querySelector('img')).toBeNull();
      expect(query(panel, '[data-testid="unpriced"]').textContent).toContain(name);
      expect(query(panel, '[data-testid="price-model"]').textContent).toBe(name);
    });
  });

  describe('the prices', () => {
    it('explains that prices are optional when there are none', async () => {
      await setup();

      expect(query(panel, '[data-testid="no-prices"]').textContent).toContain('optional');
      expect(query(panel, '[data-testid="form-title"]').textContent).toContain('Add a model price');
    });

    it('lists the prices, with the cached one only if there is one', async () => {
      await setup(costs({ prices: [SONNET, LOCAL] }));

      const first = query(panel, '[data-testid="price-1"]').textContent?.replace(/\s+/g, ' ');
      const second = query(panel, '[data-testid="price-2"]').textContent?.replace(/\s+/g, ' ');
      expect(first).toContain('claude-sonnet-5-5');
      expect(first).toContain('Input $3.0000, output $15.0000, cached input $0.3000');
      expect(second).toContain('Input $0.0000, output $0.0000 per million');
      expect(second).not.toContain('cached');
    });

    it('adds a price and shows the new costs', async () => {
      await setup(costs({ months: [month({ cost: null, unpriced_models: ['m'] })] }));
      api.savePrice.mockResolvedValue(
        costs({ prices: [SONNET], months: [month({ cost: '2.0000' })] }),
      );

      await submit({ model: ' claude-sonnet-5-5 ', input: '3', output: '15.5', cached: '0.3' });

      expect(api.savePrice).toHaveBeenCalledWith({
        model: 'claude-sonnet-5-5',
        input_per_million: 3,
        output_per_million: 15.5,
        cached_per_million: 0.3,
      });
      expect(cell('2026-11')).toBe('$2.00');
      expect(text()).toContain('The price of claude-sonnet-5-5 was saved.');
      expect(value('#price-model-name')).toBe('');
    });

    it('sends no cached price when the field is empty', async () => {
      await setup();
      api.savePrice.mockResolvedValue(costs({ prices: [LOCAL] }));

      await submit({ model: 'llama3.1:8b', input: '0', output: '0' });

      expect(api.savePrice).toHaveBeenCalledWith({
        model: 'llama3.1:8b',
        input_per_million: 0,
        output_per_million: 0,
        cached_per_million: null,
      });
    });

    it('edits a price: the model stays, the form starts from the price', async () => {
      await setup(costs({ prices: [SONNET] }));
      api.savePrice.mockResolvedValue(
        costs({ prices: [{ ...SONNET, input_per_million: '4.0000' }] }),
      );

      await click('Edit the price of claude-sonnet-5-5');

      expect(query(panel, '[data-testid="form-title"]').textContent).toContain('Edit the price of');
      expect(value('#price-model-name')).toBe('claude-sonnet-5-5');
      expect(query<HTMLInputElement>(panel, '#price-model-name').readOnly).toBe(true);
      expect(value('#price-input')).toBe('3.0000');
      expect(value('#price-cached')).toBe('0.3000');

      await submit({ input: '4' });

      expect(api.savePrice).toHaveBeenCalledWith({
        model: 'claude-sonnet-5-5',
        input_per_million: 4,
        output_per_million: 15,
        cached_per_million: 0.3,
      });
      expect(text()).toContain('Input $4.0000');
      expect(query(panel, '[data-testid="form-title"]').textContent).toContain('Add a model price');
    });

    it('leaves editing without saving', async () => {
      await setup(costs({ prices: [SONNET] }));

      await click('Edit the price of claude-sonnet-5-5');
      query<HTMLButtonElement>(panel, 'form .btn-secondary').click(); // not the dialog's Cancel
      await settle(fixture);

      expect(api.savePrice).not.toHaveBeenCalled();
      expect(value('#price-model-name')).toBe('');
      expect(query<HTMLInputElement>(panel, '#price-model-name').readOnly).toBe(false);
    });

    it('removes a price after the question and fetches the costs again', async () => {
      await setup(costs({ prices: [SONNET], months: [month({ cost: '2.0000' })] }));
      api.deletePrice.mockResolvedValue({ kind: 'deleted' });
      api.getCosts.mockResolvedValue(
        costs({ months: [month({ cost: null, unpriced_models: ['claude-sonnet-5-5'] })] }),
      );

      await click('Remove the price of claude-sonnet-5-5');
      expect(api.deletePrice).not.toHaveBeenCalled();
      expect(text()).toContain('The price of claude-sonnet-5-5 is deleted.');
      await click('Remove price');

      expect(api.deletePrice).toHaveBeenCalledWith(1);
      expect(api.getCosts).toHaveBeenCalledTimes(2);
      expect(cell('2026-11')).toContain('No price set');
      expect(panel.querySelector('[data-testid="price-1"]')).toBeNull();
      expect(text()).toContain('The price of claude-sonnet-5-5 was removed.');
    });

    it('treats a price that is gone already as removed', async () => {
      await setup(costs({ prices: [SONNET] }));
      api.deletePrice.mockResolvedValue({ kind: 'not_found' });
      api.getCosts.mockResolvedValue(costs());

      await click('Remove the price of claude-sonnet-5-5');
      await click('Remove price');

      expect(text()).toContain('was already gone');
      expect(panel.querySelector('[data-testid="price-1"]')).toBeNull();
    });

    it('does not send anything when the question is not confirmed', async () => {
      await setup(costs({ prices: [SONNET] }));

      await click('Remove the price of claude-sonnet-5-5');
      await click('Cancel');

      expect(api.deletePrice).not.toHaveBeenCalled();
      expect(panel.querySelector('[data-testid="price-1"]')).not.toBeNull();
    });

    it('shows a failed removal and keeps the list', async () => {
      await setup(costs({ prices: [SONNET] }));
      api.deletePrice.mockRejectedValue(new Error('offline'));

      await click('Remove the price of claude-sonnet-5-5');
      await click('Remove price');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(panel.querySelector('[data-testid="price-1"]')).not.toBeNull();
    });

    it('tells the page when the session is gone while saving or removing', async () => {
      await setup(costs({ prices: [SONNET] }));
      api.savePrice.mockResolvedValue({ kind: 'forbidden' });
      api.deletePrice.mockResolvedValue({ kind: 'forbidden' });

      await submit({ model: 'm', input: '1', output: '1' });
      await click('Remove the price of claude-sonnet-5-5');
      await click('Remove price');

      expect(events).toEqual(['signedOut', 'signedOut']);
    });
  });

  describe('validation', () => {
    beforeEach(() => setup());

    it('asks for all required fields and sends nothing', async () => {
      await submit({});

      expect(alerts()).toEqual([
        'Enter the name of the model.',
        'Enter a price.',
        'Enter a price.',
      ]);
      expect(api.savePrice).not.toHaveBeenCalled();
    });

    it.each(['-1', 'abc', '1e3', '1,5', '1.23456', '1000000', '0x10', ' .5'])(
      'refuses the price "%s"',
      async (price) => {
        await submit({ model: 'm', input: price, output: '1' });

        expect(alerts()).toEqual([
          'Enter a price from 0 to 999999.9999 with at most four decimal places.',
        ]);
        expect(api.savePrice).not.toHaveBeenCalled();
      },
    );

    it('accepts the largest price', async () => {
      api.savePrice.mockResolvedValue(costs());

      await submit({ model: 'm', input: '999999.9999', output: '0' });

      expect(api.savePrice).toHaveBeenCalledTimes(1);
    });

    it('refuses a cached price that is not a price', async () => {
      await submit({ model: 'm', input: '1', output: '1', cached: 'x' });

      expect(alerts()).toHaveLength(1);
      expect(api.savePrice).not.toHaveBeenCalled();
    });

    it.each(['-model', 'a b', 'a'.repeat(101), 'm<b>'])('refuses the model "%s"', async (name) => {
      await submit({ model: name, input: '1', output: '1' });

      expect(alerts()[0]).toContain('letters, digits');
      expect(api.savePrice).not.toHaveBeenCalled();
    });

    it('shows the messages of the server next to the fields', async () => {
      api.savePrice.mockResolvedValue({
        kind: 'invalid',
        errors: ['Enter a price from 0 to 999999.9999.'],
        fields: { input_per_million: ['Enter a price from 0 to 999999.9999.'] },
      });

      await submit({ model: 'm', input: '1', output: '1' });

      expect(alerts()).toEqual(['Enter a price from 0 to 999999.9999.']);
      expect(value('#price-input')).toBe('1');
    });

    it('shows messages that belong to no field above the form', async () => {
      api.savePrice.mockResolvedValue({
        kind: 'invalid',
        errors: ['You can keep at most 50 prices.'],
        fields: { non_field_errors: ['You can keep at most 50 prices.'] },
      });

      await submit({ model: 'm', input: '1', output: '1' });

      expect(alerts()).toEqual(['You can keep at most 50 prices.']);
    });

    it('shows a generic message when saving fails', async () => {
      api.savePrice.mockRejectedValue(new Error('offline'));

      await submit({ model: 'm', input: '1', output: '1' });

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });
  });

  describe('reloading', () => {
    it('fetches the costs again', async () => {
      await setup();
      api.getCosts.mockResolvedValue(costs({ months: [month()] }));

      await fixture.componentInstance.reload();
      await settle(fixture);

      expect(cell('2026-11')).toBe('$1.2345');
    });

    it('keeps what is shown and says so when it fails', async () => {
      await setup(costs({ months: [month()] }));
      api.getCosts.mockRejectedValue(new Error('offline'));

      await fixture.componentInstance.reload();
      await settle(fixture);

      expect(alerts()).toEqual(['The costs could not be refreshed. Please try again.']);
      expect(cell('2026-11')).toBe('$1.2345');
    });

    it('tells the page when the session is gone', async () => {
      await setup();
      api.getCosts.mockResolvedValue({ kind: 'forbidden' });

      await fixture.componentInstance.reload();

      expect(events).toEqual(['signedOut']);
    });
  });
});
