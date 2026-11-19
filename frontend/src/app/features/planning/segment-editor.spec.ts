import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Sport } from '../../core/planning/planning-models';
import { query } from '../../testing/dom';
import { MAX_SEGMENTS, SegmentDraft, SegmentRowError } from './edit-format';
import { SegmentEditor } from './segment-editor';

const WARMUP: SegmentDraft = {
  kind: 'warmup',
  duration: '15:00',
  repeat: '1',
  zone_system: 'pace',
  zone: '2',
};
const BLOCK: SegmentDraft = {
  kind: 'work',
  duration: '10:00',
  repeat: '3',
  zone_system: 'pace',
  zone: '4',
};
const COOLDOWN: SegmentDraft = {
  kind: 'cooldown',
  duration: '10:00',
  repeat: '1',
  zone_system: '',
  zone: '',
};

describe('SegmentEditor', () => {
  let fixture: ComponentFixture<SegmentEditor>;
  let page: HTMLElement;
  const changed = vi.fn<(rows: SegmentDraft[]) => void>();

  /** Like a parent: what is emitted becomes the rows that are passed in again. */
  function setup(
    rows: SegmentDraft[],
    sport: Sport = 'running',
    errors: SegmentRowError[] = [],
    totalError: string | null = null,
  ) {
    changed.mockClear();
    TestBed.configureTestingModule({ imports: [SegmentEditor] });
    fixture = TestBed.createComponent(SegmentEditor);
    fixture.componentRef.setInput('sport', sport);
    fixture.componentRef.setInput('rows', rows);
    fixture.componentRef.setInput('errors', errors);
    fixture.componentRef.setInput('totalError', totalError);
    fixture.componentInstance.rowsChange.subscribe((next) => {
      changed(next);
      fixture.componentRef.setInput('rows', next);
      fixture.detectChanges();
    });
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  }

  const row = (index: number) => query(page, `[data-testid="segment-row-${index}"]`);
  const rowCount = () => page.querySelectorAll('[data-testid^="segment-row-"]').length;
  const last = () => changed.mock.calls[changed.mock.calls.length - 1][0];
  const text = (testId: string) =>
    page.querySelector(`[data-testid="${testId}"]`)?.textContent?.replace(/\s+/g, ' ').trim();

  function type(index: number, field: 'repeat' | 'duration', value: string) {
    const element = query<HTMLInputElement>(row(index), `[id$="-${field}-${index}"]`);
    element.value = value;
    element.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function choose(index: number, field: 'kind' | 'system' | 'zone', value: string) {
    const element = query<HTMLSelectElement>(row(index), `[id$="-${field}-${index}"]`);
    element.value = value;
    element.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function click(testId: string, index = 0) {
    page.querySelectorAll<HTMLButtonElement>(`[data-testid="${testId}"]`)[index].click();
    fixture.detectChanges();
  }

  it('shows an empty hint and offers to add parts', () => {
    setup([]);

    expect(text('segments-empty')).toContain('No parts yet');
    expect(text('segments-total')).toBe('0 parts, total 0:00');
  });

  it('shows a row for each segment with the total of all repeats', () => {
    setup([WARMUP, BLOCK, COOLDOWN]);

    expect(rowCount()).toBe(3);
    expect(query<HTMLSelectElement>(row(1), '[id$="-kind-1"]').value).toBe('work');
    expect(query<HTMLInputElement>(row(1), '[id$="-repeat-1"]').value).toBe('3');
    expect(query<HTMLInputElement>(row(1), '[id$="-duration-1"]').value).toBe('10:00');
    expect(query<HTMLSelectElement>(row(1), '[id$="-system-1"]').value).toBe('pace');
    expect(query<HTMLSelectElement>(row(1), '[id$="-zone-1"]').value).toBe('4');
    // 15 + 3 x 10 + 10 minutes.
    expect(text('segments-total')).toBe('3 parts, total 55:00');
  });

  it('labels every field and button', () => {
    setup([WARMUP, BLOCK]);

    for (const element of Array.from(page.querySelectorAll('input, select'))) {
      expect(page.querySelector(`label[for="${element.id}"]`)).not.toBeNull();
    }
    const labels = Array.from(page.querySelectorAll('button[aria-label]')).map((button) =>
      button.getAttribute('aria-label'),
    );
    expect(labels).toContain('Move part 2 up');
    expect(labels).toContain('Remove part 1');
  });

  it('changes 3 x 10 min into 4 x 8 min', () => {
    setup([BLOCK]);

    type(0, 'repeat', '4');
    type(0, 'duration', '8:00');

    expect(last()).toEqual([{ ...BLOCK, repeat: '4', duration: '8:00' }]);
    expect(text('segments-total')).toBe('1 part, total 32:00');
  });

  it('changes the kind and clears the zone with the zone system', () => {
    setup([BLOCK]);

    choose(0, 'kind', 'recovery');
    expect(last()[0].kind).toBe('recovery');

    choose(0, 'system', 'heart_rate');
    expect(last()[0]).toMatchObject({ zone_system: 'heart_rate', zone: '' });

    choose(0, 'system', '');
    expect(last()[0]).toMatchObject({ zone_system: '', zone: '' });
    expect(row(0).querySelector('[id$="-zone-0"]')).toBeNull();
  });

  it('shows the zone select only while a zone system is chosen', () => {
    setup([COOLDOWN]);

    expect(row(0).querySelector('[id$="-zone-0"]')).toBeNull();
    choose(0, 'system', 'heart_rate');
    choose(0, 'zone', '3');

    expect(last()[0]).toMatchObject({ zone_system: 'heart_rate', zone: '3' });
    expect(row(0).querySelectorAll('[id$="-zone-0"] option')).toHaveLength(6);
  });

  it('adds a warm-up first, a block and a cool-down last', () => {
    setup([BLOCK]);

    click('add-warmup');
    click('add-block');
    click('add-cooldown');

    expect(last().map((segment) => segment.kind)).toEqual(['warmup', 'work', 'work', 'cooldown']);
    expect(last()[2].repeat).toBe('3');
    expect(rowCount()).toBe(4);
  });

  it('stops adding at the maximum number of segments', () => {
    setup(Array.from({ length: MAX_SEGMENTS - 1 }, () => ({ ...BLOCK })));

    click('add-block');
    expect(rowCount()).toBe(MAX_SEGMENTS);
    expect(text('segments-full')).toContain(`${MAX_SEGMENTS}`);
    for (const id of ['add-warmup', 'add-block', 'add-cooldown']) {
      expect(query<HTMLButtonElement>(page, `[data-testid="${id}"]`).disabled).toBe(true);
    }

    changed.mockClear();
    click('add-cooldown');
    expect(changed).not.toHaveBeenCalled();
  });

  it('moves a row up and down', () => {
    setup([WARMUP, BLOCK, COOLDOWN]);

    click('segment-down', 0);
    expect(last().map((segment) => segment.kind)).toEqual(['work', 'warmup', 'cooldown']);

    click('segment-up', 2);
    expect(last().map((segment) => segment.kind)).toEqual(['work', 'cooldown', 'warmup']);
  });

  it('cannot move the first row up or the last row down', () => {
    setup([WARMUP, COOLDOWN]);

    const up = page.querySelectorAll<HTMLButtonElement>('[data-testid="segment-up"]');
    const down = page.querySelectorAll<HTMLButtonElement>('[data-testid="segment-down"]');
    expect(up[0].disabled).toBe(true);
    expect(up[1].disabled).toBe(false);
    expect(down[0].disabled).toBe(false);
    expect(down[1].disabled).toBe(true);
  });

  it('removes a row', () => {
    setup([WARMUP, BLOCK, COOLDOWN]);

    click('segment-remove', 1);

    expect(last().map((segment) => segment.kind)).toEqual(['warmup', 'cooldown']);
    expect(rowCount()).toBe(2);
  });

  it('does not change the rows that it was given', () => {
    const rows = [{ ...BLOCK }];
    setup(rows);

    type(0, 'repeat', '5');

    expect(rows[0].repeat).toBe('3');
  });

  it('hides the zone fields for swimming', () => {
    setup([{ ...COOLDOWN, kind: 'steady' }], 'swimming');

    expect(page.querySelector('[id$="-system-0"]')).toBeNull();
    expect(page.querySelector('[id$="-zone-0"]')).toBeNull();
    expect(page.querySelector('[id$="-duration-0"]')).not.toBeNull();
  });

  it('offers only the zone systems of the sport', () => {
    setup([COOLDOWN], 'cycling');

    const values = Array.from(query<HTMLSelectElement>(page, '[id$="-system-0"]').options).map(
      (option) => option.value,
    );
    expect(values).toEqual(['', 'power', 'heart_rate']);
  });

  it('shows the errors of a row next to its fields and the error of the total', () => {
    setup(
      [WARMUP, { ...BLOCK, duration: 'abc', repeat: '0' }],
      'running',
      [{}, { duration: 'Bad duration.', repeat: 'Bad repeat.', zone: 'Choose a zone.' }],
      'Segments cannot add up to more than 24 hours.',
    );

    expect(row(0).querySelector('.field-error')).toBeNull();
    expect(row(1).querySelector('[data-testid="error-duration"]')?.textContent).toContain(
      'Bad duration.',
    );
    expect(row(1).querySelector('[data-testid="error-repeat"]')?.textContent).toContain(
      'Bad repeat.',
    );
    expect(row(1).querySelector('[data-testid="error-zone"]')?.textContent).toContain(
      'Choose a zone.',
    );
    expect(query(row(1), '[id$="-duration-1"]').getAttribute('aria-invalid')).toBe('true');
    expect(text('error-total')).toBe('Segments cannot add up to more than 24 hours.');
    // Rows that cannot be read do not count.
    expect(text('segments-total')).toBe('2 parts, total 15:00');
  });
});
