import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ReviewApi } from '../../core/review/review-api';
import {
  AskCoachResult,
  CoachComment as CoachCommentData,
  WeekReview,
} from '../../core/review/review-models';
import { dayOf, query, settle } from '../../testing/dom';
import { CoachComment } from './coach-comment';

const WEEK = '2026-11-09';
const REVIEW = { week_start: WEEK } as WeekReview;
const COMMENT: CoachCommentData = {
  comment: 'One of two done.\nKeep it easy.',
  next_week: 'reduce',
  created_at: '2026-11-15T08:00:00Z',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('CoachComment', () => {
  let askCoach: ReturnType<typeof vi.fn<(week: string) => Promise<AskCoachResult>>>;
  let fixture: ComponentFixture<CoachComment>;
  let page: HTMLElement;
  const asked = vi.fn();
  const notReviewable = vi.fn();
  const signedOut = vi.fn();
  const busy = vi.fn();

  function setup(
    inputs: { comment?: CoachCommentData | null; open?: number; disabled?: boolean } = {},
  ) {
    askCoach = vi.fn<(week: string) => Promise<AskCoachResult>>();
    for (const spy of [asked, notReviewable, signedOut, busy]) {
      spy.mockClear();
    }
    TestBed.configureTestingModule({
      imports: [CoachComment],
      providers: [provideRouter([]), { provide: ReviewApi, useValue: { askCoach } }],
    });
    fixture = TestBed.createComponent(CoachComment);
    fixture.componentRef.setInput('week', WEEK);
    fixture.componentRef.setInput('comment', inputs.comment ?? null);
    fixture.componentRef.setInput('openWorkouts', inputs.open ?? 0);
    fixture.componentRef.setInput('disabled', inputs.disabled ?? false);
    fixture.componentInstance.asked.subscribe(asked);
    fixture.componentInstance.notReviewable.subscribe(notReviewable);
    fixture.componentInstance.signedOut.subscribe(signedOut);
    fixture.componentInstance.busy.subscribe(busy);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  }

  const byId = (id: string) => page.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const button = () => query<HTMLButtonElement>(page, '[data-testid="ask"]');
  const message = () => byId('coach-message')?.textContent?.replace(/\s+/g, ' ').trim();

  async function ask() {
    button().click();
    await settle(fixture);
  }

  describe('what is shown', () => {
    it('says that the coach has not looked at the week yet, and offers to ask', () => {
      setup();

      expect(byId('coach-none')?.textContent).toContain('has not looked at this week yet');
      expect(byId('coach-text')).toBeNull();
      expect(button().textContent?.trim()).toBe('Ask the coach');
    });

    it('shows the comment as text, the recommendation in words and when it was written', () => {
      setup({ comment: COMMENT });

      expect(byId('coach-text')?.textContent).toBe('One of two done.\nKeep it easy.');
      expect(byId('coach-recommendation')?.textContent?.trim()).toBe(
        'Next week: reduce the volume',
      );
      expect(byId('coach-time')?.textContent).toContain(dayOf(COMMENT.created_at).slice(0, 6));
      expect(byId('coach-none')).toBeNull();
      expect(button().textContent?.trim()).toBe('Ask again');
    });

    it('never shows what the coach wrote as markup', () => {
      setup({
        comment: {
          ...COMMENT,
          comment: '<b>Good</b><img src=x onerror=alert(1)><script>1</script>',
        },
      });

      expect(byId('coach-text')?.textContent).toBe(
        '<b>Good</b><img src=x onerror=alert(1)><script>1</script>',
      );
      expect(page.querySelector('.coach b, .coach img, .coach script')).toBeNull();
    });

    it.each([
      ['increase', 'Next week: increase the volume a little'],
      ['hold', 'Next week: keep the volume about the same'],
      ['reduce', 'Next week: reduce the volume'],
    ] as const)('puts the recommendation %s in words', (word, expected) => {
      setup({ comment: { ...COMMENT, next_week: word } });

      expect(byId('coach-recommendation')?.textContent?.trim()).toBe(expected);
    });

    it.each([
      [0, null],
      [1, '1 workout of this week is still open. The coach is told that the week is not over.'],
      [3, '3 workouts of this week are still open. The coach is told that the week is not over.'],
    ])('says how many workouts are open (%i)', (open, expected) => {
      setup({ open });

      expect(byId('coach-open')?.textContent?.replace(/\s+/g, ' ').trim() ?? null).toBe(expected);
    });

    it('says what is sent to the provider, and that it costs', () => {
      setup();

      const text = (page.textContent ?? '').replace(/\s+/g, ' ');
      expect(text).toContain('told numbers only');
      expect(text).toContain('never your notes');
      expect(text).toContain('billed to you');
    });
  });

  describe('asking', () => {
    it('asks for the week and hands the whole week on', async () => {
      setup();
      askCoach.mockResolvedValue({ kind: 'ok', review: REVIEW });

      await ask();

      expect(askCoach).toHaveBeenCalledExactlyOnceWith(WEEK);
      expect(asked).toHaveBeenCalledExactlyOnceWith(REVIEW);
      expect(message()).toBeUndefined();
    });

    it('says that it waits, and tells the page when it starts and stops', async () => {
      setup();
      const pending = deferred<AskCoachResult>();
      askCoach.mockReturnValue(pending.promise);

      button().click();
      await fixture.whenStable();

      expect(byId('coach-waiting')?.textContent).toContain('a minute or two');
      expect(button().disabled).toBe(true);
      expect(busy.mock.calls).toEqual([[true]]);

      pending.resolve({ kind: 'ok', review: REVIEW });
      await settle(fixture);

      expect(byId('coach-waiting')).toBeNull();
      expect(busy.mock.calls).toEqual([[true], [false]]);
      expect(button().disabled).toBe(false);
    });

    it('allows one request at a time', async () => {
      setup();
      const pending = deferred<AskCoachResult>();
      askCoach.mockReturnValue(pending.promise);

      button().click();
      await fixture.whenStable();
      await fixture.componentInstance['ask']();

      expect(askCoach).toHaveBeenCalledTimes(1);
      pending.resolve({ kind: 'forbidden' });
      await settle(fixture);
    });

    it('does nothing while the page is busy', async () => {
      setup({ disabled: true });

      expect(button().disabled).toBe(true);
      await fixture.componentInstance['ask']();

      expect(askCoach).not.toHaveBeenCalled();
      expect(busy).not.toHaveBeenCalled();
    });

    it('keeps the earlier comment on view when asking fails', async () => {
      setup({ comment: COMMENT });
      askCoach.mockResolvedValue({ kind: 'rate_limited' });

      await ask();

      expect(byId('coach-text')?.textContent).toContain('One of two done.');
      expect(message()).toBe('Too many requests. Please wait a minute and try again.');
    });
  });

  describe('when it does not work', () => {
    it('says when the week cannot be reviewed any more', async () => {
      setup();
      askCoach.mockResolvedValue({ kind: 'not_reviewable' });

      await ask();

      expect(notReviewable).toHaveBeenCalledTimes(1);
      expect(asked).not.toHaveBeenCalled();
    });

    it('says when the week has nothing in it', async () => {
      setup();
      askCoach.mockResolvedValue({ kind: 'nothing_to_review' });

      await ask();

      expect(message()).toBe('There is nothing to look back on in this week yet.');
    });

    it('says when there is no provider, and where to set one up', async () => {
      setup();
      askCoach.mockResolvedValue({ kind: 'not_configured' });

      await ask();

      expect(message()).toContain('No AI provider is set up.');
      expect(byId('coach-connect')?.getAttribute('href')).toBe('/settings/connections');
    });

    it('lists what was wrong with an answer that could not be used', async () => {
      setup();
      askCoach.mockResolvedValue({
        kind: 'not_usable',
        problems: [
          { path: 'next_week', message: 'Use one of "increase", "hold", "reduce".' },
          { path: 'comment', message: 'The comment must not be empty.' },
        ],
      });

      await ask();

      expect(message()).toBe(
        'The coach did not give a comment that could be used. Please try again.',
      );
      const items = Array.from(page.querySelectorAll('[data-testid="coach-problems"] li')).map(
        (li) => li.textContent,
      );
      expect(items).toEqual([
        'Use one of "increase", "hold", "reduce".',
        'The comment must not be empty.',
      ]);
      expect(byId('coach-connect')).toBeNull();
    });

    it('shows the text of the server for a problem of the provider', async () => {
      setup();
      askCoach.mockResolvedValue({
        kind: 'provider_problem',
        problem: 'invalid_key',
        message: 'The provider did not accept the key. Check that you copied all of it.',
        retry_after: null,
      });

      await ask();

      expect(message()).toBe(
        'The provider did not accept the key. Check that you copied all of it.',
      );
    });

    it('says how long to wait when the provider asks to slow down', async () => {
      setup();
      askCoach.mockResolvedValue({
        kind: 'provider_problem',
        problem: 'rate_limited',
        message: 'The provider is asking to slow down. Please try again in a moment.',
        retry_after: 17,
      });

      await ask();

      expect(message()).toBe(
        'The provider is asking to slow down. Please try again in a moment. Try again in 17 seconds.',
      );
    });

    it('says when the limit of this server is reached', async () => {
      setup();
      askCoach.mockResolvedValue({ kind: 'rate_limited' });

      await ask();

      expect(message()).toBe('Too many requests. Please wait a minute and try again.');
    });

    it('tells the page when the session has ended', async () => {
      setup();
      askCoach.mockResolvedValue({ kind: 'forbidden' });

      await ask();

      expect(signedOut).toHaveBeenCalledTimes(1);
    });

    it('says so when the request fails, and stops waiting', async () => {
      setup();
      askCoach.mockRejectedValue(new Error('down'));

      await ask();

      expect(message()).toBe('Something went wrong. Please try again.');
      expect(busy.mock.calls).toEqual([[true], [false]]);
      expect(button().disabled).toBe(false);
    });

    it('drops the messages of an earlier try when it tries again', async () => {
      setup();
      askCoach.mockResolvedValueOnce({ kind: 'not_configured' });
      await ask();
      expect(byId('coach-connect')).toBeTruthy();

      askCoach.mockResolvedValue({ kind: 'ok', review: REVIEW });
      await ask();

      expect(message()).toBeUndefined();
      expect(byId('coach-connect')).toBeNull();
    });
  });
});
