import { Workout } from '../../core/planning/planning-models';
import {
  GOAL_CHOICES,
  SLOT_CHOICES,
  SPORT_CHOICES,
  ZONE_COUNT,
  ZONE_SYSTEMS_OF,
  addDays,
  blankWorkout,
  checkNotes,
  checkTitle,
  dayChoices,
  editedFrom,
  parseDuration,
  parseStretching,
  zoneChoices,
  zoneSystemChoices,
} from './edit-format';

describe('edit-format', () => {
  describe('days', () => {
    it.each([
      ['2026-11-16', 0, '2026-11-16'],
      ['2026-11-16', 6, '2026-11-22'],
      ['2026-11-30', 1, '2026-12-01'],
      ['2026-12-28', 7, '2027-01-04'],
      ['2028-02-28', 1, '2028-02-29'],
      ['2026-11-16', -7, '2026-11-09'],
    ])('adds days to %s (%i)', (date, days, expected) => {
      expect(addDays(date, days)).toBe(expected);
    });

    it('offers the seven days of the week, Monday first', () => {
      const days = dayChoices('2026-11-16');

      expect(days.map((day) => day.value)).toEqual([
        '2026-11-16',
        '2026-11-17',
        '2026-11-18',
        '2026-11-19',
        '2026-11-20',
        '2026-11-21',
        '2026-11-22',
      ]);
      expect(days[0].label).toBe('Mon 16 Nov');
      expect(days[6].label).toBe('Sun 22 Nov');
    });
  });

  describe('choices', () => {
    it('names the sports and the goals the server knows', () => {
      expect(SPORT_CHOICES.map((c) => c.value)).toEqual([
        'running',
        'cycling',
        'swimming',
        'strength',
      ]);
      expect(GOAL_CHOICES.map((c) => c.value)).toEqual([
        'recovery',
        'endurance',
        'tempo',
        'threshold',
        'vo2max',
        'strength',
        'other',
      ]);
    });

    it('offers no time of day first, then the three of the format', () => {
      expect(SLOT_CHOICES.map((c) => c.value)).toEqual(['', 'morning', 'afternoon', 'evening']);
      expect(SLOT_CHOICES[0].label).toBe('Not said');
    });

    it.each([
      ['running', ['pace', 'heart_rate']],
      ['cycling', ['power', 'heart_rate']],
      ['swimming', []],
      ['strength', []],
    ] as const)('offers the zone systems that fit %s', (sport, systems) => {
      expect(zoneSystemChoices(sport).map((c) => c.value)).toEqual(systems);
      expect(ZONE_SYSTEMS_OF[sport]).toEqual(systems);
    });

    it('offers as many zones as the system has', () => {
      expect(ZONE_COUNT).toEqual({ power: 7, heart_rate: 5, pace: 5 });
      expect(zoneChoices('power').map((z) => z.value)).toEqual([1, 2, 3, 4, 5, 6, 7]);
      expect(zoneChoices('pace')).toHaveLength(5);
      expect(zoneChoices('heart_rate')[0]).toEqual({ value: 1, label: 'Zone 1' });
    });
  });

  describe('parseDuration', () => {
    it.each([
      ['90', 90],
      [' 45 ', 45],
      ['1', 1],
      ['1440', 1440],
      ['1:30', 90],
      ['0:45', 45],
      ['24:00', 1440],
      ['01:05', 65],
    ])('reads %j as %i minutes', (text, minutes) => {
      expect(parseDuration(text)).toEqual({ ok: true, value: minutes });
    });

    it.each(['', '  ', 'abc', '1.5', '-5', '1:60', '1:5', '1h30', '99999', '1,5', '١٢'])(
      'refuses %j as no duration',
      (text) => {
        const result = parseDuration(text);

        expect(result.ok).toBe(false);
      },
    );

    it.each(['0', '1441', '25:00', '0:00'])('refuses %j as outside a minute to a day', (text) => {
      expect(parseDuration(text)).toEqual({
        ok: false,
        error: 'Use a duration from 1 minute to 24 hours.',
      });
    });

    it('says how to write it', () => {
      expect(parseDuration('lots')).toEqual({
        ok: false,
        error: 'Enter the duration as minutes (90) or hours and minutes (1:30).',
      });
    });
  });

  describe('parseStretching', () => {
    it.each([
      ['', 0],
      ['  ', 0],
      ['0', 0],
      ['10', 10],
      ['60', 60],
    ])('reads %j as %i', (text, minutes) => {
      expect(parseStretching(text)).toEqual({ ok: true, value: minutes });
    });

    it.each(['61', '-1', '1.5', 'x', '1000'])('refuses %j', (text) => {
      expect(parseStretching(text)).toEqual({
        ok: false,
        error: 'Enter whole minutes from 0 to 60.',
      });
    });
  });

  describe('checkTitle', () => {
    it('accepts a title of 1 to 100 characters after trimming', () => {
      expect(checkTitle('Easy run')).toBeNull();
      expect(checkTitle('  x  ')).toBeNull();
      expect(checkTitle('t'.repeat(100))).toBeNull();
      expect(checkTitle(`  ${'t'.repeat(100)}  `)).toBeNull();
    });

    it('refuses an empty title and one that is too long', () => {
      expect(checkTitle('')).toBe('Enter a title.');
      expect(checkTitle('   ')).toBe('Enter a title.');
      expect(checkTitle('t'.repeat(101))).toBe('Use at most 100 characters.');
    });

    it.each(['one\ntwo', 'tab\there', 'bell\u0007', 'null\u0000byte', 'a\u2028b', 'a\u2029b'])(
      'refuses %j: a title is one line',
      (title) => {
        expect(checkTitle(title)).toBe('A title is one line of plain text.');
      },
    );
  });

  describe('checkNotes', () => {
    it('accepts nothing, text and several lines', () => {
      expect(checkNotes('')).toBeNull();
      expect(checkNotes('Keep it easy')).toBeNull();
      expect(checkNotes('one\ntwo\n\nthree')).toBeNull();
      expect(checkNotes('n'.repeat(500))).toBeNull();
    });

    it('refuses notes that are too long', () => {
      expect(checkNotes('n'.repeat(501))).toBe('Use at most 500 characters.');
    });

    it.each(['bell\u0007', 'tab\there', 'null\u0000byte', 'a\u2028b', 'a\u2029b', 'a\rb'])(
      'refuses %j',
      (notes) => {
        expect(checkNotes(notes)).toBe('Notes are plain text.');
      },
    );
  });

  describe('editedFrom', () => {
    const WORKOUT: Workout = {
      lineage: '01a1d73d-aaaa-7000-8000-000000000001',
      day: '2026-11-18',
      sport: 'running',
      title: 'Intervals',
      goal: 'threshold',
      duration_minutes: 70,
      zone_system: 'pace',
      zone: 4,
      target: { low: 240, high: 260, unit: 's/km' },
      export: { status: 'synced', error_code: '', pushed_at: '2026-11-14T08:00:00Z' },
      notes: 'Hard',
      slot: 'morning',
      stretching_minutes: 10,
      segments: [
        {
          kind: 'work',
          seconds: 600,
          repeat: 3,
          zone_system: 'pace',
          zone: 4,
          target: { low: 240, high: 260, unit: 's/km' },
        },
      ],
    };

    it('keeps everything that is part of the plan, lineage included', () => {
      expect(editedFrom(WORKOUT)).toEqual({
        lineage: '01a1d73d-aaaa-7000-8000-000000000001',
        day: '2026-11-18',
        sport: 'running',
        title: 'Intervals',
        goal: 'threshold',
        duration_minutes: 70,
        zone_system: 'pace',
        zone: 4,
        notes: 'Hard',
        slot: 'morning',
        stretching_minutes: 10,
        segments: [{ kind: 'work', seconds: 600, repeat: 3, zone_system: 'pace', zone: 4 }],
      });
    });

    it('leaves out what the server works out or knows', () => {
      const text = JSON.stringify(editedFrom(WORKOUT));

      expect(text).not.toContain('target');
      expect(text).not.toContain('export');
    });

    it('makes copies of the segments', () => {
      const edited = editedFrom(WORKOUT);

      expect(edited.segments[0]).not.toBe(WORKOUT.segments[0]);
    });
  });

  describe('blankWorkout', () => {
    it('is an easy hour of running without a lineage', () => {
      expect(blankWorkout('2026-11-17')).toEqual({
        lineage: null,
        day: '2026-11-17',
        sport: 'running',
        title: '',
        goal: 'endurance',
        duration_minutes: 60,
        zone_system: null,
        zone: null,
        notes: '',
        slot: null,
        stretching_minutes: 0,
        segments: [],
      });
    });
  });
});
