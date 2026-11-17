import { DatePipe } from '@angular/common';
import { Component, input, output } from '@angular/core';
import { PlanStatus } from '../core/planning/planning-models';
import { STATUS_LABELS } from '../features/planning/plan-format';

/** What a chip needs to know of a version of a plan (of a week or of the season). */
export interface ChipVersion {
  id: string;
  version: number;
  status: PlanStatus;
  created_at: string;
}

/**
 * The versions of a plan as a row of chips that scrolls sideways on a narrow screen. The text is
 * short ("v2 · Draft"); the full name and the date are in the accessible name. The version that is
 * shown is marked with `aria-current`.
 */
@Component({
  selector: 'app-version-chips',
  imports: [DatePipe],
  template: `
    <ul
      class="versions m-0 mb-4 flex snap-x list-none gap-2 overflow-x-auto p-0 pb-1"
      [attr.aria-label]="label()"
    >
      @for (version of versions(); track version.id) {
        <li class="flex-none snap-start">
          <button
            type="button"
            class="cursor-pointer whitespace-nowrap rounded-full border border-border bg-surface px-3 py-1 text-sm text-fg disabled:cursor-progress disabled:opacity-60 aria-[current=true]:border-accent aria-[current=true]:bg-accent-soft aria-[current=true]:font-semibold aria-[current=true]:text-accent"
            [disabled]="disabled()"
            [attr.aria-current]="selected() === version.id ? 'true' : null"
            [attr.aria-label]="
              'Version ' +
              version.version +
              ', ' +
              status[version.status] +
              ', ' +
              (version.created_at | date: 'MMM d, HH:mm')
            "
            [attr.data-testid]="'version-' + version.version"
            (click)="opened.emit(version.id)"
          >
            v{{ version.version }} · {{ status[version.status] }}
          </button>
        </li>
      }
    </ul>
  `,
})
export class VersionChips {
  readonly versions = input.required<readonly ChipVersion[]>();
  /** The id of the version that is shown. */
  readonly selected = input<string | null>(null);
  readonly disabled = input(false);
  /** The name of the list for screen readers. */
  readonly label = input('Versions');

  readonly opened = output<string>();

  protected readonly status = STATUS_LABELS;
}
