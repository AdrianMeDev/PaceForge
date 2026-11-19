import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { SegmentKind, Sport, ZoneSystem } from '../../core/planning/planning-models';
import {
  MAX_SEGMENTS,
  SEGMENT_KIND_CHOICES,
  SegmentDraft,
  SegmentRowError,
  blankSegment,
  formatSegmentDuration,
  parseSegmentDuration,
  parseSegmentRepeat,
  zoneChoices,
  zoneSystemChoices,
} from './edit-format';

let nextId = 0;

/**
 * The rows of an interval structure: warm-up, steady or repeated blocks, cool-down. The rows are
 * the text of the fields (`SegmentDraft`) and every change is sent as a new list; the parent keeps
 * them, checks them with `parseSegmentDrafts` and passes the messages back as `errors` and
 * `totalError`.
 */
@Component({
  selector: 'app-segment-editor',
  templateUrl: './segment-editor.html',
  styleUrl: './segment-editor.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SegmentEditor {
  readonly sport = input.required<Sport>();
  readonly rows = input.required<readonly SegmentDraft[]>();
  /** The messages of the rows, in the order of the rows; a row may have none. */
  readonly errors = input<readonly SegmentRowError[]>([]);
  /** The message about all rows together (too many, more than a day). */
  readonly totalError = input<string | null>(null);
  readonly rowsChange = output<SegmentDraft[]>();

  protected readonly id = `segments-${nextId++}`;
  protected readonly kinds = SEGMENT_KIND_CHOICES;
  protected readonly zones = zoneChoices;
  protected readonly maxSegments = MAX_SEGMENTS;
  protected readonly zoneSystems = computed(() => zoneSystemChoices(this.sport()));
  protected readonly full = computed(() => this.rows().length >= MAX_SEGMENTS);
  /** The length of all rows that can be read, repeats counted. */
  protected readonly total = computed(() => {
    let seconds = 0;
    for (const row of this.rows()) {
      const duration = parseSegmentDuration(row.duration);
      const repeat = parseSegmentRepeat(row.repeat);
      if (duration.ok && repeat.ok) {
        seconds += duration.value * repeat.value;
      }
    }
    return formatSegmentDuration(seconds);
  });

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  protected setKind(index: number, value: string): void {
    this.patch(index, { kind: value as SegmentKind });
  }

  protected setZoneSystem(index: number, value: string): void {
    this.patch(index, { zone_system: value as ZoneSystem | '', zone: '' });
  }

  protected patch(index: number, change: Partial<SegmentDraft>): void {
    this.rowsChange.emit(
      this.rows().map((row, at) => (at === index ? { ...row, ...change } : { ...row })),
    );
  }

  protected addWarmup(): void {
    this.add({ ...blankSegment(), kind: 'warmup', duration: '10:00' }, 0);
  }

  protected addBlock(): void {
    this.add({ ...blankSegment(), repeat: '3' });
  }

  protected addCooldown(): void {
    this.add({ ...blankSegment(), kind: 'cooldown', duration: '10:00' });
  }

  protected move(index: number, by: -1 | 1): void {
    const target = index + by;
    if (target < 0 || target >= this.rows().length) {
      return;
    }
    const rows = this.rows().map((row) => ({ ...row }));
    [rows[index], rows[target]] = [rows[target], rows[index]];
    this.rowsChange.emit(rows);
  }

  protected remove(index: number): void {
    this.rowsChange.emit(
      this.rows()
        .filter((_, at) => at !== index)
        .map((row) => ({ ...row })),
    );
  }

  /** Add `row` at `position` (the end if none), unless the list is full. */
  private add(row: SegmentDraft, position = this.rows().length): void {
    if (this.full()) {
      return;
    }
    const rows = this.rows().map((existing) => ({ ...existing }));
    rows.splice(position, 0, row);
    this.rowsChange.emit(rows);
  }
}
