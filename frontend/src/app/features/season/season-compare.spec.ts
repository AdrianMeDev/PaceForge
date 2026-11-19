import { KeySession, PlanWeek, SeasonPlan } from '../../core/season/season-models';
import { compareSeasons, compareWeeks } from './season-compare';

const LONG: KeySession = { sport: 'running', kind: 'long', minutes: 90, detail: '' };
const TEMPO: KeySession = { sport: 'cycling', kind: 'tempo', minutes: 45, detail: '3 x 10 min' };

function week(start: string, changes: Partial<PlanWeek> = {}): PlanWeek {
  const minutes = changes.minutes ?? { running: 120, cycling: 60 };
  return {
    week_start: start,
    minutes,
    total_minutes: Object.values(minutes).reduce((sum, value) => sum + value, 0),
    planned_load: { running: 110, cycling: 55 },
    total_planned_load: 165,
    focus: 'endurance',
    key_sessions: [LONG],
    reason: 'Build.',
    done: null,
    done_load: null,
    ...changes,
  };
}

function plan(weeks: PlanWeek[], rationale = 'The season.'): SeasonPlan {
  return {
    id: '0195f3a0-0000-7000-8000-000000000001',
    version: 1,
    status: 'confirmed',
    reason: '',
    request: '',
    rationale,
    parent: null,
    created_at: '2026-11-16T10:00:00Z',
    confirmed_at: '2026-11-16T10:00:00Z',
    skeleton: {
      rolling: true,
      truncated: false,
      main_race: null,
      peak_minutes: 300,
      weeks: [],
    },
    weeks,
    report: null,
  };
}

const W1 = '2026-11-16';
const W2 = '2026-11-23';
const W3 = '2026-11-30';

describe('compareSeasons', () => {
  const base = plan([week(W1), week(W2), week(W3)]);

  it('finds nothing between a version and itself', () => {
    expect(compareSeasons(base, base)).toEqual({
      weeks: [],
      unchanged: 3,
      rationale: null,
      only_in_changed: [],
      only_in_base: [],
    });
  });

  it('finds nothing between two versions with the same content', () => {
    const copy = plan(base.weeks.map((w) => structuredClone(w)));

    expect(compareSeasons(base, copy).weeks).toEqual([]);
  });

  it('lists only the weeks that differ, in order, and counts the others', () => {
    const changed = plan([week(W1), week(W2, { focus: 'tempo' }), week(W3, { reason: 'Easier.' })]);

    const found = compareSeasons(base, changed);

    expect(found.weeks.map((w) => w.week_start)).toEqual([W2, W3]);
    expect(found.unchanged).toBe(1);
  });

  it('finds the sports whose minutes differ, with the minutes of the week', () => {
    const changed = plan([
      week(W1),
      week(W2, { minutes: { running: 120, cycling: 30 } }),
      week(W3),
    ]);

    const [difference] = compareSeasons(base, changed).weeks;

    expect(difference.minutes).toEqual([{ sport: 'cycling', before: 60, after: 30 }]);
    expect(difference.total).toEqual({ before: 180, after: 150 });
    expect(difference.focus).toBeNull();
    expect(difference.sessions_added).toEqual([]);
    expect(difference.reason).toBeNull();
  });

  it('finds a sport that was added or dropped', () => {
    const changed = plan([
      week(W1, { minutes: { running: 120, swimming: 40 } }),
      week(W2),
      week(W3),
    ]);

    const [difference] = compareSeasons(base, changed).weeks;

    expect(difference.minutes).toEqual([
      { sport: 'cycling', before: 60, after: 0 },
      { sport: 'swimming', before: 0, after: 40 },
    ]);
  });

  it('finds a changed focus', () => {
    const changed = plan([week(W1, { focus: 'threshold' }), week(W2), week(W3)]);

    expect(compareSeasons(base, changed).weeks[0].focus).toEqual({
      before: 'endurance',
      after: 'threshold',
    });
  });

  it('finds key sessions that were added and removed', () => {
    const changed = plan([week(W1, { key_sessions: [TEMPO] }), week(W2), week(W3)]);

    const [difference] = compareSeasons(base, changed).weeks;

    expect(difference.sessions_added).toEqual([TEMPO]);
    expect(difference.sessions_removed).toEqual([LONG]);
  });

  it('counts a key session whose length or words changed as removed and added', () => {
    const longer = { ...LONG, minutes: 120 };
    const changed = plan([week(W1, { key_sessions: [longer] }), week(W2), week(W3)]);

    const [difference] = compareSeasons(base, changed).weeks;

    expect(difference.sessions_added).toEqual([longer]);
    expect(difference.sessions_removed).toEqual([LONG]);
  });

  it('does not mind the order of the key sessions', () => {
    const before = plan([week(W1, { key_sessions: [LONG, TEMPO] })]);
    const after = plan([week(W1, { key_sessions: [TEMPO, LONG] })]);

    expect(compareSeasons(before, after).weeks).toEqual([]);
  });

  it('counts a key session that occurs twice twice', () => {
    const before = plan([week(W1, { key_sessions: [LONG, LONG] })]);
    const after = plan([week(W1, { key_sessions: [LONG] })]);

    const [difference] = compareSeasons(before, after).weeks;

    expect(difference.sessions_removed).toEqual([LONG]);
    expect(difference.sessions_added).toEqual([]);
  });

  it('finds a reason that was written differently', () => {
    const changed = plan([week(W1, { reason: 'Less cycling.' }), week(W2), week(W3)]);

    expect(compareSeasons(base, changed).weeks[0].reason).toEqual({
      before: 'Build.',
      after: 'Less cycling.',
    });
  });

  it('finds a rationale that was written differently', () => {
    const changed = plan(base.weeks, 'Another season.');

    expect(compareSeasons(base, changed).rationale).toEqual({
      before: 'The season.',
      after: 'Another season.',
    });
    expect(compareSeasons(base, changed).weeks).toEqual([]);
  });

  it('names the weeks that only one version has', () => {
    const changed = plan([week(W1), week(W3), week('2026-12-07')]);

    const found = compareSeasons(base, changed);

    expect(found.only_in_changed).toEqual(['2026-12-07']);
    expect(found.only_in_base).toEqual([W2]);
    expect(found.unchanged).toBe(2);
  });

  it('is the same answer for the same versions', () => {
    const changed = plan([week(W1, { focus: 'tempo' }), week(W2), week(W3)]);

    expect(compareSeasons(base, changed)).toEqual(compareSeasons(base, changed));
  });

  it('does not change the versions', () => {
    const changed = plan([week(W1, { key_sessions: [TEMPO] }), week(W2), week(W3)]);
    const snapshot = structuredClone([base, changed]);

    compareSeasons(base, changed);

    expect([base, changed]).toEqual(snapshot);
  });
});

describe('compareWeeks', () => {
  it('ignores dynamic load estimates and activity totals when comparing plan content', () => {
    expect(
      compareWeeks(
        week(W1),
        week(W1, {
          planned_load: { running: 150 },
          total_planned_load: 150,
          done: [{ sport: 'running', minutes: 60 }],
          done_load: [{ sport: 'running', load: 70 }],
        }),
      ),
    ).toBeNull();
  });
  it('is null for the same week', () => {
    expect(compareWeeks(week(W1), week(W1))).toBeNull();
  });

  it('keeps the texts of the coach as they are', () => {
    const hostile = '<img src=x onerror=alert(1)>';

    const found = compareWeeks(week(W1), week(W1, { reason: hostile }));

    expect(found?.reason?.after).toBe(hostile);
  });
});
