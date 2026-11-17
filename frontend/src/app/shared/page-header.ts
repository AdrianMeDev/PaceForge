import { Component, input } from '@angular/core';

/**
 * How a page starts: its title (the one `h1` of the page), a short line under it and, on the right,
 * the main action of the page (projected: `<app-page-header title="…"><button …/></app-page-header>`).
 * On a narrow screen the action goes under the title.
 */
@Component({
  selector: 'app-page-header',
  template: `
    <header class="mb-6 flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div class="min-w-0">
        <h1 class="text-2xl font-semibold tracking-tight">{{ title() }}</h1>
        @if (subtitle(); as text) {
          <p class="mt-1 text-muted" data-testid="subtitle">{{ text }}</p>
        }
      </div>
      <div class="flex flex-wrap items-center gap-2 empty:hidden" data-testid="actions">
        <ng-content />
      </div>
    </header>
  `,
  styles: `
    h1 {
      margin: 0;
    }
  `,
})
export class PageHeader {
  readonly title = input.required<string>();
  readonly subtitle = input('');
}
