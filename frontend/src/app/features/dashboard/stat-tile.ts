import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * One figure with a label, a line of detail and, optionally, a bar that shows how far along it is
 * (`progress` in percent; `null`: no bar). A bar beyond 100 is full.
 */
@Component({
  selector: 'app-stat-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="h-full rounded-md border border-border bg-surface p-4 shadow-card">
      <p class="text-sm text-muted" data-testid="label">{{ label() }}</p>
      <p class="mt-1 text-2xl font-semibold" data-testid="value">{{ value() }}</p>
      @if (detail(); as text) {
        <p class="text-sm text-muted" data-testid="detail">{{ text }}</p>
      }
      @if (width(); as percent) {
        <div
          class="mt-3 h-2 overflow-hidden rounded-full bg-surface-2"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          [attr.aria-valuenow]="percent.value"
          [attr.aria-label]="label()"
        >
          <div class="h-full rounded-full bg-accent" [style.width.%]="percent.value"></div>
        </div>
      }
    </div>
  `,
})
export class StatTile {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly detail = input('');
  readonly progress = input<number | null>(null);

  protected readonly width = computed(() => {
    const progress = this.progress();
    return progress === null ? null : { value: Math.max(0, Math.min(100, Math.round(progress))) };
  });
}
