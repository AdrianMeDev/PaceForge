import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReviewApi } from '../../core/review/review-api';
import {
  FeedbackInput,
  SaveFeedbackResult,
  WeekFeedback,
  WeekReview,
} from '../../core/review/review-models';
import { query, settle } from '../../testing/dom';
import { WeekFeedbackForm } from './week-feedback-form';

const WEEK = '2026-11-02';
const REVIEW = { week_start: WEEK } as WeekReview;

const STORED: WeekFeedback = {
  fatigue: 4,
  motivation: null,
  pain: 1,
  verdict: 'good',
  notes: 'Heavy legs',
  updated_at: '2026-11-08T08:00:00Z',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe('WeekFeedbackForm', () => {
  let saveFeedback: ReturnType<
    typeof vi.fn<(week: string, input: FeedbackInput) => Promise<SaveFeedbackResult>>
  >;
  let fixture: ComponentFixture<WeekFeedbackForm>;
  let page: HTMLElement;
  const saved = vi.fn();
  const closed = vi.fn();
  const notReviewable = vi.fn();
  const signedOut = vi.fn();

  function setup(feedback: WeekFeedback | null = null, disabled = false) {
    saveFeedback = vi.fn<(week: string, input: FeedbackInput) => Promise<SaveFeedbackResult>>();
    saved.mockClear();
    closed.mockClear();
    notReviewable.mockClear();
    signedOut.mockClear();
    TestBed.configureTestingModule({
      imports: [WeekFeedbackForm],
      providers: [{ provide: ReviewApi, useValue: { saveFeedback } }],
    });
    fixture = TestBed.createComponent(WeekFeedbackForm);
    fixture.componentRef.setInput('week', WEEK);
    fixture.componentRef.setInput('feedback', feedback);
    fixture.componentRef.setInput('disabled', disabled);
    fixture.componentInstance.saved.subscribe(saved);
    fixture.componentInstance.closed.subscribe(closed);
    fixture.componentInstance.notReviewable.subscribe(notReviewable);
    fixture.componentInstance.signedOut.subscribe(signedOut);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  }

  const scale = (field: string) => query<HTMLSelectElement>(page, `#feedback-${field}`);
  const note = () => query<HTMLTextAreaElement>(page, '#feedback-notes');
  const saveButton = () => query<HTMLButtonElement>(page, '[data-testid="feedback-save"]');
  const closeButton = () => query<HTMLButtonElement>(page, '[data-testid="feedback-close"]');
  const verdict = () => query<HTMLSelectElement>(page, '#feedback-verdict');
  const nextNote = () => query<HTMLTextAreaElement>(page, '#next-week-note');
  const fieldErrors = () =>
    Array.from(page.querySelectorAll('.field-error')).map((e) => e.textContent?.trim());
  const message = () => page.querySelector('[data-testid="feedback-message"]')?.textContent?.trim();

  function fill(values: Partial<Record<'fatigue' | 'motivation' | 'pain', string>>, notes = '') {
    for (const [field, value] of Object.entries(values)) {
      scale(field).value = value;
      scale(field).dispatchEvent(new Event('change'));
    }
    note().value = notes;
    note().dispatchEvent(new Event('input'));
  }

  function judge(value: string) {
    verdict().value = value;
    verdict().dispatchEvent(new Event('change'));
  }

  function tell(text: string) {
    nextNote().value = text;
    nextNote().dispatchEvent(new Event('input'));
  }

  async function submit() {
    saveButton().click();
    await settle(fixture);
  }

  async function close() {
    closeButton().click();
    await settle(fixture);
  }

  it('offers the three scales from 1 to 5 in words, and none', () => {
    setup();

    const labels = Array.from(page.querySelectorAll('label')).map((l) => l.textContent?.trim());
    expect(labels).toEqual([
      'Tiredness',
      'Motivation',
      'Pain',
      'The week as a whole',
      'Note (optional)',
      'What should the coach know about next week? (optional)',
    ]);
    const options = Array.from(scale('pain').options).map((o) => [o.value, o.textContent?.trim()]);
    expect(options).toEqual([
      ['', '–'],
      ['1', '1 – None'],
      ['2', '2 – Slight'],
      ['3', '3 – Noticeable'],
      ['4', '4 – Strong'],
      ['5', '5 – Severe'],
    ]);
  });

  it('offers the four verdicts and none', () => {
    setup();

    const options = Array.from(verdict().options).map((o) => [o.value, o.textContent?.trim()]);
    expect(options).toEqual([
      ['', '–'],
      ['bad', 'Bad'],
      ['fair', 'Fair'],
      ['good', 'Good'],
      ['strong', 'Strong'],
    ]);
  });

  it('says that the note stays with the user and what the coach is told', () => {
    setup();

    expect(page.textContent).toContain('Your note stays with you');
    expect(page.textContent).toContain('how you judge the week');
  });

  it('starts empty without feedback', () => {
    setup();

    expect(scale('fatigue').value).toBe('');
    expect(scale('motivation').value).toBe('');
    expect(scale('pain').value).toBe('');
    expect(verdict().value).toBe('');
    expect(note().value).toBe('');
    expect(nextNote().value).toBe('');
  });

  it('shows the stored feedback', () => {
    setup(STORED);

    expect(scale('fatigue').value).toBe('4');
    expect(scale('motivation').value).toBe('');
    expect(scale('pain').value).toBe('1');
    expect(verdict().value).toBe('good');
    expect(note().value).toBe('Heavy legs');
  });

  it('sends the scales and the trimmed note for the week, and hands the week on', async () => {
    setup();
    saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
    fill({ fatigue: '4', motivation: '2', pain: '1' }, '  Heavy legs ');
    judge('strong');

    await submit();

    expect(saveFeedback).toHaveBeenCalledExactlyOnceWith(WEEK, {
      fatigue: 4,
      motivation: 2,
      pain: 1,
      verdict: 'strong',
      notes: 'Heavy legs',
    });
    expect(saved).toHaveBeenCalledExactlyOnceWith(REVIEW);
    expect(closed).not.toHaveBeenCalled();
  });

  it('sends what is left empty as empty: nothing at all removes the feedback', async () => {
    setup(STORED);
    saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
    fill({ fatigue: '', pain: '' }, '');
    judge('');

    await submit();

    expect(saveFeedback).toHaveBeenCalledExactlyOnceWith(WEEK, {
      fatigue: null,
      motivation: null,
      pain: null,
      verdict: null,
      notes: '',
    });
  });

  it('follows what is stored when the page shows the saved feedback', () => {
    setup();
    fill({ fatigue: '2' }, 'typed');

    fixture.componentRef.setInput('feedback', STORED);
    fixture.detectChanges();

    expect(scale('fatigue').value).toBe('4');
    expect(verdict().value).toBe('good');
    expect(note().value).toBe('Heavy legs');
  });

  it('keeps a verdict that was not touched when the rest is saved', async () => {
    setup(STORED);
    saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
    fill({ fatigue: '2' }, 'Heavy legs');

    await submit();

    expect(saveFeedback.mock.calls[0][1].verdict).toBe('good');
  });

  it('sends nothing for a verdict that is none of the four', async () => {
    setup();
    saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
    judge('great');

    await submit();

    expect(saveFeedback.mock.calls[0][1].verdict).toBeNull();
  });

  it('shows the message of the server about the verdict', async () => {
    setup();
    saveFeedback.mockResolvedValue({
      kind: 'invalid',
      errors: { verdict: ['Choose one of the verdicts.'] },
      message: null,
    });

    await submit();

    expect(fieldErrors()).toEqual(['Choose one of the verdicts.']);
    expect(verdict().getAttribute('aria-invalid')).toBe('true');
  });

  it('refuses a note that is too long without asking the server', async () => {
    setup();
    fill({ fatigue: '3' }, 'x'.repeat(501));

    await submit();

    expect(saveFeedback).not.toHaveBeenCalled();
    expect(fieldErrors()).toEqual(['Use at most 500 characters.']);
  });

  it('takes a note of exactly the limit', async () => {
    setup();
    saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
    fill({}, 'x'.repeat(500));

    await submit();

    expect(saveFeedback).toHaveBeenCalledTimes(1);
  });

  it('shows the messages of the server next to the fields and keeps the entries', async () => {
    setup();
    saveFeedback.mockResolvedValue({
      kind: 'invalid',
      errors: {
        fatigue: ['Ensure this value is less than or equal to 5.'],
        notes: ['Must not contain control characters.', 'x'],
      },
      message: null,
    });
    fill({ fatigue: '3', pain: '2' }, 'my note');

    await submit();

    expect(fieldErrors()).toEqual([
      'Ensure this value is less than or equal to 5.',
      'Must not contain control characters.',
    ]);
    expect(scale('fatigue').value).toBe('3');
    expect(scale('pain').value).toBe('2');
    expect(note().value).toBe('my note');
    expect(saved).not.toHaveBeenCalled();
  });

  it('shows a general refusal', async () => {
    setup();
    saveFeedback.mockResolvedValue({
      kind: 'invalid',
      errors: {},
      message: 'Your entries could not be saved. Please check them.',
    });

    await submit();

    expect(message()).toBe('Your entries could not be saved. Please check them.');
  });

  it('says so when saving fails, and clears the message when it tries again', async () => {
    setup();
    saveFeedback.mockRejectedValueOnce(new Error('down'));
    await submit();
    expect(message()).toBe('Something went wrong. Please try again.');

    saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
    await submit();

    expect(message()).toBeUndefined();
    expect(saved).toHaveBeenCalledTimes(1);
  });

  it('tells the page when the week cannot be reviewed any more', async () => {
    setup();
    saveFeedback.mockResolvedValue({ kind: 'not_reviewable' });

    await submit();

    expect(notReviewable).toHaveBeenCalledTimes(1);
    expect(saved).not.toHaveBeenCalled();
  });

  it('tells the page when the session has ended', async () => {
    setup();
    saveFeedback.mockResolvedValue({ kind: 'forbidden' });

    await submit();

    expect(signedOut).toHaveBeenCalledTimes(1);
  });

  it('allows one thing at a time', async () => {
    setup();
    const pending = deferred<SaveFeedbackResult>();
    saveFeedback.mockReturnValue(pending.promise);

    saveButton().click();
    await fixture.whenStable();

    expect(saveButton().disabled).toBe(true);
    expect(scale('fatigue').disabled).toBe(true);
    expect(note().disabled).toBe(true);
    saveButton().click();
    expect(saveFeedback).toHaveBeenCalledTimes(1);

    pending.resolve({ kind: 'forbidden' });
    await settle(fixture);
    expect(saveButton().disabled).toBe(false);
  });

  it('does nothing while the page is busy', async () => {
    setup(null, true);

    expect(saveButton().disabled).toBe(true);
    await fixture.componentInstance['submit'](false);
    expect(saveFeedback).not.toHaveBeenCalled();
  });
  describe('closing the week', () => {
    it('saves the feedback with the verdict, then hands the week and the note on', async () => {
      setup();
      saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
      fill({ fatigue: '3' }, 'Own note');
      judge('fair');
      tell('  No time on Tuesday.\nA trip on Saturday. ');

      await close();

      expect(saveFeedback).toHaveBeenCalledExactlyOnceWith(WEEK, {
        fatigue: 3,
        motivation: null,
        pain: null,
        verdict: 'fair',
        notes: 'Own note',
      });
      expect(closed).toHaveBeenCalledExactlyOnceWith({
        review: REVIEW,
        note: 'No time on Tuesday.\nA trip on Saturday.',
      });
      expect(saved).not.toHaveBeenCalled();
    });

    it('hands on an empty note when there is none', async () => {
      setup();
      saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });

      await close();

      expect(closed).toHaveBeenCalledExactlyOnceWith({ review: REVIEW, note: '' });
    });

    it('does not send the note for the next week to the server with the feedback', async () => {
      setup();
      saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
      tell('For the coach');

      await close();

      expect(JSON.stringify(saveFeedback.mock.calls[0][1])).not.toContain('For the coach');
    });

    it('does not close when the feedback was refused, and keeps both notes', async () => {
      setup();
      saveFeedback.mockResolvedValue({
        kind: 'invalid',
        errors: { notes: ['Must not contain control characters.'] },
        message: null,
      });
      fill({}, 'my note');
      tell('for the coach');

      await close();

      expect(closed).not.toHaveBeenCalled();
      expect(fieldErrors()).toEqual(['Must not contain control characters.']);
      expect(note().value).toBe('my note');
      expect(nextNote().value).toBe('for the coach');
    });

    it('refuses a note for the next week that is too long, before saving anything', async () => {
      setup();
      tell('x'.repeat(301));

      await close();

      expect(saveFeedback).not.toHaveBeenCalled();
      expect(closed).not.toHaveBeenCalled();
      expect(fieldErrors()).toEqual(['Use at most 300 characters.']);
      expect(nextNote().getAttribute('aria-invalid')).toBe('true');
    });

    it('takes a note of exactly the limit', async () => {
      setup();
      saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
      tell('x'.repeat(300));

      await close();

      expect(closed).toHaveBeenCalledTimes(1);
    });

    it('does not mind the note for the next week when only the feedback is saved', async () => {
      setup();
      saveFeedback.mockResolvedValue({ kind: 'ok', review: REVIEW });
      tell('x'.repeat(301));

      await submit();

      expect(saved).toHaveBeenCalledTimes(1);
      expect(fieldErrors()).toEqual([]);
    });

    it('tells the page when the week cannot be reviewed or the session has ended', async () => {
      setup();
      saveFeedback.mockResolvedValueOnce({ kind: 'not_reviewable' });
      await close();
      saveFeedback.mockResolvedValueOnce({ kind: 'forbidden' });
      await close();

      expect(notReviewable).toHaveBeenCalledTimes(1);
      expect(signedOut).toHaveBeenCalledTimes(1);
      expect(closed).not.toHaveBeenCalled();
    });

    it('allows one thing at a time', async () => {
      setup();
      const pending = deferred<SaveFeedbackResult>();
      saveFeedback.mockReturnValue(pending.promise);

      closeButton().click();
      await fixture.whenStable();

      expect(closeButton().disabled).toBe(true);
      expect(nextNote().disabled).toBe(true);
      closeButton().click();
      expect(saveFeedback).toHaveBeenCalledTimes(1);
      pending.resolve({ kind: 'forbidden' });
      await settle(fixture);
      expect(closeButton().disabled).toBe(false);
    });

    it('does nothing while the page is busy', async () => {
      setup(null, true);

      expect(closeButton().disabled).toBe(true);
      await fixture.componentInstance['submit'](true);
      expect(saveFeedback).not.toHaveBeenCalled();
    });

    it('says what closing does and costs', () => {
      setup();

      expect(page.textContent).toContain('billed to your AI provider');
      expect(page.textContent).toContain('Nothing is confirmed without you');
    });
  });
});
