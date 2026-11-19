import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { SeasonApi } from '../core/season/season-api';
import { SeasonChangeReason, SeasonReassessment } from '../core/season/season-models';

type State =
  | { kind: 'hidden' | 'loading' | 'signed_out' | 'unavailable' }
  | { kind: 'notice'; reassessment: SeasonReassessment; id: string; version: number };

const REASON_TEXT: Record<SeasonChangeReason, string> = {
  baseline_unknown:
    'The original inputs of your confirmed season are unknown. Consider a new draft.',
  goals_changed: 'Your active goals have changed since this season was drafted.',
  ftp_changed: 'Your effective cycling FTP has changed since this season was drafted.',
  best_times_changed: 'Your best times have changed since this season was drafted.',
  training_time_changed: 'Your available training time has changed substantially.',
  training_deviation:
    'Training in each of the latest three completed weeks was below 70% or above 130% of planned minutes. Consider adjusting your season.',
};

/** A read-only hint. Parents can call reload() after saving inputs or confirming a plan. */
@Component({
  selector: 'app-season-change-notice',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let current = state();
    @if (current.kind === 'notice') {
      <aside class="notice notice-warning mb-4" role="status" data-testid="season-change-notice">
        <p class="font-semibold">Your confirmed season may need an adjustment.</p>
        <ul class="list-disc pl-5">
          @for (reason of current.reassessment.reasons; track reason) {
            <li>{{ reasonText[reason] }}</li>
          }
        </ul>
        <ng-content />
        <a routerLink="/season" [queryParams]="{ change: current.id }" fragment="season-change"
          >Ask for a change to confirmed version {{ current.version }}</a
        >
      </aside>
    } @else if (current.kind === 'signed_out') {
      <p class="notice notice-warning mb-4" role="status">
        Your session has ended. Please sign in again.
        <a routerLink="/login">Go to sign in</a>
      </p>
    } @else if (current.kind === 'unavailable') {
      <div class="notice notice-warning mb-4" role="status">
        Season adjustment status is unavailable.
        <button type="button" class="btn btn-secondary btn-sm" (click)="reload()">Retry</button>
      </div>
    }
  `,
})
export class SeasonChangeNotice implements OnInit {
  private readonly api = inject(SeasonApi);
  private readonly destroyRef = inject(DestroyRef);
  private request = 0;
  protected readonly state = signal<State>({ kind: 'hidden' });
  protected readonly reasonText = REASON_TEXT;

  /** Evidence Mondays for the active notice, empty unless training deviation is shown. */
  readonly deviationWeeks = computed<readonly string[]>(() => {
    const current = this.state();
    return current.kind === 'notice' ? current.reassessment.deviation_weeks : [];
  });

  ngOnInit(): void {
    void this.reload();
  }

  /** Replaces old hints immediately; only the latest live request may publish a result. */
  async reload(): Promise<void> {
    const request = ++this.request;
    const stale = () => this.destroyRef.destroyed || request !== this.request;
    this.state.set({ kind: 'loading' });
    try {
      const result = await this.api.reassessment();
      if (stale()) return;
      if (result.kind === 'forbidden') {
        this.state.set({ kind: 'signed_out' });
        return;
      }
      const reassessment = result.reassessment;
      const id = reassessment.confirmed_plan_id;
      if (id === null || reassessment.reasons.length === 0) {
        this.state.set({ kind: 'hidden' });
        return;
      }
      const versions = await this.api.plans();
      if (stale()) return;
      if (versions.kind === 'forbidden') {
        this.state.set({ kind: 'signed_out' });
        return;
      }
      const confirmed = versions.plans.find(
        (plan) => plan.id === id && plan.status === 'confirmed',
      );
      // Confirmation may have changed between the two reads. Never link to another version.
      this.state.set(
        confirmed
          ? { kind: 'notice', reassessment, id, version: confirmed.version }
          : { kind: 'unavailable' },
      );
    } catch {
      if (!stale()) this.state.set({ kind: 'unavailable' });
    }
  }
}
