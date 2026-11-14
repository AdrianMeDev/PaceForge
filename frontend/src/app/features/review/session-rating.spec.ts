import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivitiesApi } from '../../core/activities/activities-api';
import { RateActivityResult, RatingInput } from '../../core/activities/activities-models';
import { ReviewActivity } from '../../core/review/review-models';
import { query, settle } from '../../testing/dom';
import { SessionRating } from './session-rating';

function activity(changes: Partial<ReviewActivity> = {}): ReviewActivity {
  return {
    id: 'a1',
    source: 'manual',
    sport: 'running',
    start_time: '2026-11-02T07:00:00Z',
    day: '2026-11-02',
    elapsed_seconds: null,
    timer_seconds: 3600,
    distance_m: null,
    rpe: null,
    notes: '',
    load: null,
    workout_id: 'w1',
    ...changes,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('SessionRating', () => {
  let rate: ReturnType<
    typeof vi.fn<(id: string, input: RatingInput) => Promise<RateActivityResult>>
  >;
  let fixture: ComponentFixture<SessionRating>;
  let page: HTMLElement;
  const rated = vi.fn();
  const gone = vi.fn();
  const signedOut = vi.fn();

  function setup(shown: ReviewActivity = activity(), disabled = false) {
    rate = vi.fn<(id: string, input: RatingInput) => Promise<RateActivityResult>>();
    rated.mockClear();
    gone.mockClear();
    signedOut.mockClear();
    TestBed.configureTestingModule({
      imports: [SessionRating],
      providers: [{ provide: ActivitiesApi, useValue: { rate } }],
    });
    fixture = TestBed.createComponent(SessionRating);
    fixture.componentRef.setInput('activity', shown);
    fixture.componentRef.setInput('disabled', disabled);
    fixture.componentInstance.rated.subscribe(rated);
    fixture.componentInstance.gone.subscribe(gone);
    fixture.componentInstance.signedOut.subscribe(signedOut);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  }

  const select = () => query<HTMLSelectElement>(page, '#rpe-a1');
  const note = () => query<HTMLTextAreaElement>(page, '#notes-a1');
  const saveButton = () => query<HTMLButtonElement>(page, '[data-testid="rating-save-a1"]');
  const fieldErrors = () =>
    Array.from(page.querySelectorAll('.field-error')).map((e) => e.textContent?.trim());
  const message = () => page.querySelector('[data-testid="rating-message"]')?.textContent?.trim();

  function fill(rpe: string, notes: string) {
    select().value = rpe;
    select().dispatchEvent(new Event('change'));
    note().value = notes;
    note().dispatchEvent(new Event('input'));
  }

  async function submit() {
    saveButton().click();
    await settle(fixture);
  }

  it('offers to rate a session that is not rated, and to change a rating that is', () => {
    setup();
    expect(page.querySelector('summary')?.textContent?.trim()).toBe('Rate this session');

    fixture.componentRef.setInput('activity', activity({ rpe: 6 }));
    fixture.detectChanges();
    expect(page.querySelector('summary')?.textContent?.trim()).toBe('Change the rating');
  });

  it('offers the ratings from 1 to 10 in words, and none', () => {
    setup();

    const options = Array.from(select().options).map((o) => [o.value, o.textContent?.trim()]);
    expect(options[0]).toEqual(['', '–']);
    expect(options[1]).toEqual(['1', '1 – Very easy']);
    expect(options[10]).toEqual(['10', '10 – Maximal']);
    expect(options.length).toBe(11);
  });

  it('shows what is stored', () => {
    setup(activity({ rpe: 7, notes: 'Hilly' }));

    expect(select().value).toBe('7');
    expect(note().value).toBe('Hilly');
  });

  it('sends the rating and the note, trimmed, and tells the page', async () => {
    setup();
    rate.mockResolvedValue({ kind: 'ok', activity: {} as never });
    fill('7', '  Legs were heavy \n');

    await submit();

    expect(rate).toHaveBeenCalledExactlyOnceWith('a1', { rpe: 7, notes: 'Legs were heavy' });
    expect(rated).toHaveBeenCalledTimes(1);
    expect(message()).toBeUndefined();
  });

  it('sends a cleared rating as null and an empty note', async () => {
    setup(activity({ rpe: 7, notes: 'Hilly' }));
    rate.mockResolvedValue({ kind: 'ok', activity: {} as never });
    fill('', '');

    await submit();

    expect(rate).toHaveBeenCalledExactlyOnceWith('a1', { rpe: null, notes: '' });
  });

  it('follows what is stored when the page shows the saved rating', async () => {
    setup();
    fill('4', 'typed');

    fixture.componentRef.setInput('activity', activity({ rpe: 8, notes: 'saved' }));
    fixture.detectChanges();

    expect(select().value).toBe('8');
    expect(note().value).toBe('saved');
  });

  it('refuses a note that is too long without asking the server', async () => {
    setup();
    fill('5', 'x'.repeat(501));

    await submit();

    expect(rate).not.toHaveBeenCalled();
    expect(fieldErrors()).toEqual(['Use at most 500 characters.']);
    expect(rated).not.toHaveBeenCalled();
  });

  it('takes a note of exactly the limit', async () => {
    setup();
    rate.mockResolvedValue({ kind: 'ok', activity: {} as never });
    fill('5', 'x'.repeat(500));

    await submit();

    expect(rate).toHaveBeenCalledTimes(1);
  });

  it('shows the messages of the server next to the fields and keeps the entries', async () => {
    setup();
    rate.mockResolvedValue({
      kind: 'invalid',
      errors: {
        rpe: ['Ensure this value is less than or equal to 10.'],
        notes: ['Too long.', 'x'],
      },
      message: null,
    });
    fill('3', 'my note');

    await submit();

    expect(fieldErrors()).toEqual(['Ensure this value is less than or equal to 10.', 'Too long.']);
    expect(select().value).toBe('3');
    expect(note().value).toBe('my note');
    expect(rated).not.toHaveBeenCalled();
  });

  it('shows a general refusal', async () => {
    setup();
    rate.mockResolvedValue({
      kind: 'invalid',
      errors: {},
      message: 'The rating could not be saved. Please check your entries.',
    });

    await submit();

    expect(message()).toBe('The rating could not be saved. Please check your entries.');
  });

  it('clears an old message when it tries again', async () => {
    setup();
    rate.mockRejectedValueOnce(new Error('down'));
    await submit();
    expect(message()).toBe('Something went wrong. Please try again.');

    rate.mockResolvedValue({ kind: 'ok', activity: {} as never });
    await submit();

    expect(message()).toBeUndefined();
    expect(rated).toHaveBeenCalledTimes(1);
  });

  it('tells the page when the session is gone', async () => {
    setup();
    rate.mockResolvedValue({ kind: 'not_found' });

    await submit();

    expect(gone).toHaveBeenCalledTimes(1);
    expect(rated).not.toHaveBeenCalled();
  });

  it('tells the page when the session has ended', async () => {
    setup();
    rate.mockResolvedValue({ kind: 'forbidden' });

    await submit();

    expect(signedOut).toHaveBeenCalledTimes(1);
  });

  it('allows one thing at a time', async () => {
    setup();
    const pending = deferred<RateActivityResult>();
    rate.mockReturnValue(pending.promise);

    saveButton().click();
    await fixture.whenStable();

    expect(saveButton().disabled).toBe(true);
    expect(select().disabled).toBe(true);
    expect(note().disabled).toBe(true);
    saveButton().click();
    expect(rate).toHaveBeenCalledTimes(1);

    pending.resolve({ kind: 'forbidden' });
    await settle(fixture);
    expect(saveButton().disabled).toBe(false);
  });

  it('does nothing while the page is busy', async () => {
    setup(activity(), true);

    expect(saveButton().disabled).toBe(true);
    expect(select().disabled).toBe(true);
    await fixture.componentInstance['submit']();
    expect(rate).not.toHaveBeenCalled();
  });
});
