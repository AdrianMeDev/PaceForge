import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { InvitationsApi } from '../../core/admin/invitations-api';
import { Invitation, InvitationStatus } from '../../core/admin/invitations-models';
import { PageHeader } from '../../shared/page-header';

type View = 'loading' | 'unreachable' | 'ready' | 'mfa_required' | 'forbidden';
type Copied = 'idle' | 'copied' | 'failed';

/**
 * The link and the address it belongs to, shown once after an invitation was created or sent
 * again. `emailSent` tells whether the mail went out; `resent` tells which action it was.
 */
interface IssuedLink {
  email: string;
  url: string;
  emailSent: boolean;
  resent: boolean;
}

const FALLBACK = 'Something went wrong. Please try again.';
const RATE_LIMITED =
  'Too many invitation emails were sent. Please wait a few minutes and try again.';

const STATUS_LABELS: Record<InvitationStatus, string> = {
  pending: 'Pending',
  used: 'Used',
  revoked: 'Revoked',
  expired: 'Expired',
};

/**
 * Where administrators invite people. The server keeps only a hash of the token, so the link
 * exists in the answer to the creating request and nowhere else: this page shows it once and
 * forgets it when it is dismissed or the page is left. The server also sends the link by
 * email; the link on this page is the fallback when that mail did not arrive.
 */
@Component({
  selector: 'app-invitations-page',
  imports: [ReactiveFormsModule, RouterLink, DatePipe, PageHeader],
  templateUrl: './invitations-page.html',
  styleUrl: './invitations-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvitationsPage implements OnInit {
  private readonly api = inject(InvitationsApi);

  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
  });

  protected readonly view = signal<View>('loading');
  protected readonly invitations = signal<Invitation[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly issued = signal<IssuedLink | null>(null);
  protected readonly copied = signal<Copied>('idle');
  /** The invitation the administrator is being asked to confirm revoking. */
  protected readonly confirming = signal<string | null>(null);
  protected readonly expiredCount = computed(
    () => this.invitations().filter((invitation) => invitation.status === 'expired').length,
  );

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected label(status: InvitationStatus): string {
    return STATUS_LABELS[status];
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      await this.refresh();
    } catch {
      this.view.set('unreachable');
    }
  }

  protected async create(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.errors.set([]);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.busy.set(true);
    try {
      const result = await this.api.create(this.form.getRawValue().email.trim());
      switch (result.kind) {
        case 'created':
          this.issued.set({
            email: result.invitation.email,
            url: result.inviteUrl,
            emailSent: result.emailSent,
            resent: false,
          });
          this.copied.set('idle');
          this.form.reset();
          await this.refreshQuietly();
          break;
        case 'invalid':
          this.errors.set(result.errors);
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMITED]);
          break;
        default:
          this.view.set(result.kind);
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected async copy(): Promise<void> {
    const link = this.issued();
    if (link === null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(link.url);
      this.copied.set('copied');
    } catch {
      this.copied.set('failed');
    }
  }

  /** Selects the whole link when the field gets focus, so that copying by hand is one step. */
  protected select(event: Event): void {
    (event.target as HTMLInputElement).select();
  }

  protected dismissLink(): void {
    this.issued.set(null);
    this.copied.set('idle');
  }

  protected ask(invitation: Invitation): void {
    this.errors.set([]);
    this.confirming.set(invitation.id);
  }

  protected cancelRevoke(): void {
    this.confirming.set(null);
  }

  /** Issues a new link for a pending or expired invitation and mails it again. */
  protected async resend(invitation: Invitation): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.errors.set([]);
    this.confirming.set(null);
    this.busy.set(true);
    try {
      const result = await this.api.resend(invitation.id);
      switch (result.kind) {
        case 'resent':
          this.issued.set({
            email: result.invitation.email,
            url: result.inviteUrl,
            emailSent: result.emailSent,
            resent: true,
          });
          this.copied.set('idle');
          break;
        case 'conflict':
          this.errors.set([
            `The invitation for ${invitation.email} has been used or revoked already.`,
          ]);
          break;
        case 'not_found':
          this.errors.set([`The invitation for ${invitation.email} no longer exists.`]);
          break;
        case 'rate_limited':
          this.errors.set([RATE_LIMITED]);
          return;
        default:
          this.view.set(result.kind);
          return;
      }
      await this.refreshQuietly();
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  protected async revoke(invitation: Invitation): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.errors.set([]);
    this.busy.set(true);
    try {
      const result = await this.api.revoke(invitation.id);
      this.confirming.set(null);
      switch (result.kind) {
        case 'revoked':
          break;
        case 'conflict':
          this.errors.set([`The invitation for ${invitation.email} has been used already.`]);
          break;
        case 'not_found':
          this.errors.set([`The invitation for ${invitation.email} no longer exists.`]);
          break;
        default:
          this.view.set(result.kind);
          return;
      }
      await this.refreshQuietly();
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.busy.set(false);
    }
  }

  /** Loads the list and shows it; refusals switch the whole page. Rejects when unreachable. */
  private async refresh(): Promise<void> {
    const result = await this.api.list();
    if (result.kind === 'ok') {
      this.invitations.set(result.invitations);
      this.view.set('ready');
    } else {
      this.view.set(result.kind);
    }
  }

  /** After an action: a list that cannot be reloaded must not hide what the action achieved. */
  private async refreshQuietly(): Promise<void> {
    try {
      await this.refresh();
    } catch {
      this.errors.update((errors) => [...errors, 'The list could not be refreshed.']);
    }
  }
}
