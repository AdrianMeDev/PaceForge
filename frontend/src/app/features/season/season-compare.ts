import { Focus, KeySession, PlanWeek, SeasonPlan, Sport } from '../../core/season/season-models';

const SPORTS: Sport[] = ['running', 'cycling', 'swimming', 'strength'];

/** Before and after of one thing that differs. */
export interface Change<T> {
  before: T;
  after: T;
}

/** What differs in one week. Only the parts that differ are set. */
export interface WeekDifference {
  week_start: string;
  /** The sports whose minutes differ, in the order of the sports. */
  minutes: { sport: Sport; before: number; after: number }[];
  /** The minutes of the whole week, if they differ. */
  total: Change<number> | null;
  focus: Change<Focus> | null;
  /** Key sessions the changed version has and the old one did not, and the other way round. */
  sessions_added: KeySession[];
  sessions_removed: KeySession[];
  /** The reason of the week, if it was written differently (the coach's own words). */
  reason: Change<string> | null;
}

/** What differs between two versions of a season plan. */
export interface SeasonDifferences {
  /** The weeks that differ, in the order of the changed version. */
  weeks: WeekDifference[];
  /** How many weeks are the same in both. */
  unchanged: number;
  /** The rationale, if it was written differently. */
  rationale: Change<string> | null;
  /** Weeks that only one of the versions has (the same skeleton gives none). */
  only_in_changed: string[];
  only_in_base: string[];
}

/**
 * What the version `changed` does differently from the version `base`, week by week (weeks are
 * matched by their Monday): the minutes of each sport, the focus, the key sessions and the
 * reason, and the rationale. Pure. The same versions give the same answer, and a version
 * compared with itself differs in nothing.
 */
export function compareSeasons(base: SeasonPlan, changed: SeasonPlan): SeasonDifferences {
  const before = new Map(base.weeks.map((week) => [week.week_start, week]));
  const weeks: WeekDifference[] = [];
  const only_in_changed: string[] = [];
  let unchanged = 0;
  for (const week of changed.weeks) {
    const old = before.get(week.week_start);
    if (old === undefined) {
      only_in_changed.push(week.week_start);
      continue;
    }
    before.delete(week.week_start);
    const difference = compareWeeks(old, week);
    if (difference === null) {
      unchanged += 1;
    } else {
      weeks.push(difference);
    }
  }
  return {
    weeks,
    unchanged,
    rationale:
      base.rationale === changed.rationale
        ? null
        : { before: base.rationale, after: changed.rationale },
    only_in_changed,
    only_in_base: [...before.keys()],
  };
}

/** The differences of one week, or `null` if there are none. */
export function compareWeeks(base: PlanWeek, changed: PlanWeek): WeekDifference | null {
  const minutes = SPORTS.flatMap((sport) => {
    const was = base.minutes[sport] ?? 0;
    const now = changed.minutes[sport] ?? 0;
    return was === now ? [] : [{ sport, before: was, after: now }];
  });
  const { added, removed } = compareSessions(base.key_sessions, changed.key_sessions);
  const difference: WeekDifference = {
    week_start: changed.week_start,
    minutes,
    total:
      base.total_minutes === changed.total_minutes
        ? null
        : { before: base.total_minutes, after: changed.total_minutes },
    focus: base.focus === changed.focus ? null : { before: base.focus, after: changed.focus },
    sessions_added: added,
    sessions_removed: removed,
    reason: base.reason === changed.reason ? null : { before: base.reason, after: changed.reason },
  };
  const same =
    minutes.length === 0 &&
    difference.total === null &&
    difference.focus === null &&
    added.length === 0 &&
    removed.length === 0 &&
    difference.reason === null;
  return same ? null : difference;
}

/** The key sessions that are only in one list; one that occurs twice must occur twice in both. */
function compareSessions(
  base: KeySession[],
  changed: KeySession[],
): { added: KeySession[]; removed: KeySession[] } {
  const rest = [...base];
  const added: KeySession[] = [];
  for (const session of changed) {
    const found = rest.findIndex((candidate) => sameSession(candidate, session));
    if (found === -1) {
      added.push(session);
    } else {
      rest.splice(found, 1);
    }
  }
  return { added, removed: rest };
}

function sameSession(a: KeySession, b: KeySession): boolean {
  return (
    a.sport === b.sport && a.kind === b.kind && a.minutes === b.minutes && a.detail === b.detail
  );
}
