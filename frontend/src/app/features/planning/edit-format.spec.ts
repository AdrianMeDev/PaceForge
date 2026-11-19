import { EditedSegment, Workout } from '../../core/planning/planning-models';
import {
  GOAL_CHOICES,
  MAX_SEGMENTS,
  REPEAT_MAX,
  SEGMENT_KIND_CHOICES,
  SEGMENT_SECONDS_MAX,
  SLOT_CHOICES,
  SPORT_CHOICES,
  ZONE_COUNT,
  ZONE_SYSTEMS_OF,
  addDays,
  blankSegment,
  blankWorkout,
  checkNotes,
  checkSegmentsTotal,
  checkTitle,
  dayChoices,
  draftsFromSegments,
  editedFrom,
  formatSegmentDuration,
  parseDuration,
  parseSegmentDrafts,
  parseSegmentDuration,
  parseSegmentRepeat,
  parseStretching,
  sanitizeSegmentZones,
  segmentsDurationMinutes,
  segmentsTotalSeconds,
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
      estimated_load: 117,
      zone_system: 'pace',
      zone: 4,
      target: { low: 240, high: 260, unit: 's/km' },
      export: { status: 'synced', error_code: '', pushed_at: '2026-11-14T08:00:00Z' },
      notes: 'Hard',
      slot: 'morning',
      stretching_minutes: 10,
      exercises: [],
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
        exercises: [],
        segments: [{ kind: 'work', seconds: 600, repeat: 3, zone_system: 'pace', zone: 4 }],
      });
    });

    it('leaves out what the server works out or knows', () => {
      const text = JSON.stringify(editedFrom(WORKOUT));

      expect(text).not.toContain('target');
      expect(text).not.toContain('export');
      expect(text).not.toContain('estimated_load');
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
        exercises: [],
        segments: [],
      });
    });
  });

  describe('segment limits and choices', () => {
    it('matches the schema limits', () => {
      expect(MAX_SEGMENTS).toBe(40);
      expect(SEGMENT_SECONDS_MAX).toBe(86_400);
      expect(REPEAT_MAX).toBe(50);
    });

    it('offers every segment kind in schema order', () => {
      expect(SEGMENT_KIND_CHOICES.map((choice) => choice.value)).toEqual([
        'warmup',
        'steady',
        'work',
        'recovery',
        'cooldown',
      ]);
    });
  });

  describe('parseSegmentDuration and formatSegmentDuration', () => {
    it.each([
      ['1', 1],
      ['45', 45],
      [' 90 ', 90],
      ['86400', 86_400],
      ['0:01', 1],
      ['0:45', 45],
      ['1:30', 90],
      ['10:00', 600],
      ['90:00', 5400],
      ['1:00:00', 3600],
      ['24:00:00', 86_400],
    ])('reads %j as %i seconds', (text, seconds) => {
      expect(parseSegmentDuration(text)).toEqual({ ok: true, value: seconds });
    });

    it.each(['', '  ', 'abc', '1.5', '-5', '1:60', '1:5', '1:00:60', '1h30', '999999'])(
      'refuses %j as invalid format',
      (text) => {
        expect(parseSegmentDuration(text).ok).toBe(false);
      },
    );

    it.each(['0', '0:00', '0:00:00', '86401', '24:00:01', '25:00:00'])(
      'refuses %j as outside 1 second to 24 hours',
      (text) => {
        expect(parseSegmentDuration(text)).toEqual({
          ok: false,
          error: 'Use a duration from 1 second to 24 hours.',
        });
      },
    );

    it.each([
      [1, '0:01'],
      [45, '0:45'],
      [90, '1:30'],
      [600, '10:00'],
      [3599, '59:59'],
      [3600, '1:00:00'],
      [5430, '1:30:30'],
      [86_400, '24:00:00'],
    ])('formats %i seconds as %s and parses back', (seconds, formatted) => {
      expect(formatSegmentDuration(seconds)).toBe(formatted);
      expect(parseSegmentDuration(formatted)).toEqual({ ok: true, value: seconds });
    });
  });

  describe('parseSegmentRepeat', () => {
    it.each([
      ['1', 1],
      [' 4 ', 4],
      ['50', 50],
    ])('reads %j as %i repeats', (text, repeat) => {
      expect(parseSegmentRepeat(text)).toEqual({ ok: true, value: repeat });
    });

    it.each(['', '  ', '0', '51', '-1', '1.5', 'abc', '1000'])(
      'refuses %j outside 1 to 50',
      (text) => {
        expect(parseSegmentRepeat(text)).toEqual({
          ok: false,
          error: 'Enter whole repeats from 1 to 50.',
        });
      },
    );
  });

  describe('segment drafts and totals', () => {
    const SEGMENTS: EditedSegment[] = [
      { kind: 'warmup', seconds: 600, repeat: 1, zone_system: 'power', zone: 1 },
      { kind: 'work', seconds: 300, repeat: 4, zone_system: 'power', zone: 4 },
      { kind: 'cooldown', seconds: 300, repeat: 1, zone_system: null, zone: null },
    ];

    it('creates a valid blank segment draft', () => {
      const blank = blankSegment();

      expect(blank).toEqual({
        kind: 'work',
        duration: '5:00',
        repeat: '1',
        zone_system: '',
        zone: '',
      });
      expect(parseSegmentDrafts([blank])).toEqual({
        ok: true,
        segments: [{ kind: 'work', seconds: 300, repeat: 1, zone_system: null, zone: null }],
      });
    });

    it('converts segments to drafts and parses them back', () => {
      const drafts = draftsFromSegments(SEGMENTS);

      expect(drafts).toEqual([
        { kind: 'warmup', duration: '10:00', repeat: '1', zone_system: 'power', zone: '1' },
        { kind: 'work', duration: '5:00', repeat: '4', zone_system: 'power', zone: '4' },
        { kind: 'cooldown', duration: '5:00', repeat: '1', zone_system: '', zone: '' },
      ]);
      expect(parseSegmentDrafts(drafts)).toEqual({ ok: true, segments: SEGMENTS });
    });

    it('reports row errors for invalid duration, repeat, and missing or out-of-range zone', () => {
      const result = parseSegmentDrafts([
        { kind: 'work', duration: '0', repeat: '0', zone_system: 'pace', zone: '' },
        { kind: 'steady', duration: '5:00', repeat: '1', zone_system: 'pace', zone: '6' },
      ]);

      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.error).toBeNull();
        expect(result.rowErrors).toEqual([
          {
            duration: 'Use a duration from 1 second to 24 hours.',
            repeat: 'Enter whole repeats from 1 to 50.',
            zone: 'Choose a zone.',
          },
          { zone: 'Choose a zone.' },
        ]);
      }
    });

    it('refuses more than MAX_SEGMENTS rows', () => {
      const drafts = Array.from({ length: MAX_SEGMENTS + 1 }, () => blankSegment());
      const result = parseSegmentDrafts(drafts);

      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.error).toBe('Use at most 40 segments.');
      }
    });

    it('computes total seconds and rounds duration minutes with a 1-minute floor', () => {
      expect(segmentsTotalSeconds([])).toBe(0);
      expect(segmentsDurationMinutes([])).toBe(0);
      expect(segmentsTotalSeconds(SEGMENTS)).toBe(2100);
      expect(segmentsDurationMinutes(SEGMENTS)).toBe(35);

      expect(
        segmentsDurationMinutes([
          { kind: 'work', seconds: 20, repeat: 1, zone_system: null, zone: null },
        ]),
      ).toBe(1);
      expect(
        segmentsDurationMinutes([
          { kind: 'work', seconds: 89, repeat: 1, zone_system: null, zone: null },
        ]),
      ).toBe(1);
      expect(
        segmentsDurationMinutes([
          { kind: 'work', seconds: 90, repeat: 1, zone_system: null, zone: null },
        ]),
      ).toBe(2);
    });

    it('enforces the 24-hour cap across segments', () => {
      const exactDay: EditedSegment[] = [
        { kind: 'steady', seconds: 43_200, repeat: 2, zone_system: null, zone: null },
      ];
      expect(checkSegmentsTotal(exactDay)).toBeNull();

      const overDay: EditedSegment[] = [
        { kind: 'steady', seconds: 43_200, repeat: 2, zone_system: null, zone: null },
        { kind: 'cooldown', seconds: 1, repeat: 1, zone_system: null, zone: null },
      ];
      expect(checkSegmentsTotal(overDay)).toBe('Segments cannot add up to more than 24 hours.');

      const parsed = parseSegmentDrafts(draftsFromSegments(overDay));
      expect(parsed.ok).toBe(false);
      if (!parsed.ok) {
        expect(parsed.error).toBe('Segments cannot add up to more than 24 hours.');
      }
    });
  });

  describe('sanitizeSegmentZones', () => {
    const DRAFTS = [
      {
        kind: 'warmup' as const,
        duration: '10:00',
        repeat: '1',
        zone_system: 'heart_rate' as const,
        zone: '2',
      },
      {
        kind: 'work' as const,
        duration: '5:00',
        repeat: '4',
        zone_system: 'power' as const,
        zone: '4',
      },
      {
        kind: 'recovery' as const,
        duration: '2:00',
        repeat: '4',
        zone_system: 'pace' as const,
        zone: '1',
      },
      {
        kind: 'cooldown' as const,
        duration: '5:00',
        repeat: '1',
        zone_system: '' as const,
        zone: '',
      },
    ];

    it('keeps compatible zone systems and clears incompatible ones on sport change', () => {
      expect(sanitizeSegmentZones(DRAFTS, 'running')).toEqual([
        { kind: 'warmup', duration: '10:00', repeat: '1', zone_system: 'heart_rate', zone: '2' },
        { kind: 'work', duration: '5:00', repeat: '4', zone_system: '', zone: '' },
        { kind: 'recovery', duration: '2:00', repeat: '4', zone_system: 'pace', zone: '1' },
        { kind: 'cooldown', duration: '5:00', repeat: '1', zone_system: '', zone: '' },
      ]);

      expect(sanitizeSegmentZones(DRAFTS, 'cycling')).toEqual([
        { kind: 'warmup', duration: '10:00', repeat: '1', zone_system: 'heart_rate', zone: '2' },
        { kind: 'work', duration: '5:00', repeat: '4', zone_system: 'power', zone: '4' },
        { kind: 'recovery', duration: '2:00', repeat: '4', zone_system: '', zone: '' },
        { kind: 'cooldown', duration: '5:00', repeat: '1', zone_system: '', zone: '' },
      ]);
    });

    it('clears all segment zones when switching to swimming or strength', () => {
      for (const sport of ['swimming', 'strength'] as const) {
        expect(sanitizeSegmentZones(DRAFTS, sport)).toEqual([
          { kind: 'warmup', duration: '10:00', repeat: '1', zone_system: '', zone: '' },
          { kind: 'work', duration: '5:00', repeat: '4', zone_system: '', zone: '' },
          { kind: 'recovery', duration: '2:00', repeat: '4', zone_system: '', zone: '' },
          { kind: 'cooldown', duration: '5:00', repeat: '1', zone_system: '', zone: '' },
        ]);
      }
    });
  });
});
