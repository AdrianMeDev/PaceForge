import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ChatApi } from '../../core/chat/chat-api';
import { ChatMessage } from '../../core/chat/chat-models';
import { weekRange } from '../planning/plan-format';
import { ConfirmDialog } from '../../shared/confirm-dialog';
import { PageHeader } from '../../shared/page-header';

type View = 'loading' | 'unreachable' | 'ready' | 'signed_out';

/** The longest message the server takes (`USER_TEXT_MAX` in `backend/chat/models.py`). */
export const TEXT_MAX = 2000;
const FALLBACK = 'Something went wrong. Please try again.';
const TOO_MANY = 'Too many messages in a short time. Please wait a minute and try again.';
const NOT_CONFIGURED = 'No AI provider is set up, so your coach cannot answer.';
const DELETE_FAILED = 'The conversation could not be deleted. Please try again.';

/**
 * The chat with the coach: the athlete asks a question or says what should change, and the coach
 * answers. A change is never made in place: the coach proposes it, the server makes a new draft of
 * a week or of the season from it, and the card under the answer says what changed and links to the
 * draft, where it is confirmed or discarded. Every text is shown as text only.
 * Asking takes a while (a minute or two) and costs the user a request to their own AI provider, so
 * it only ever happens when the button is pressed; one thing at a time.
 */
@Component({
  selector: 'app-chat-page',
  imports: [DatePipe, RouterLink, ConfirmDialog, PageHeader],
  templateUrl: './chat-page.html',
})
export class ChatPage implements OnInit {
  private readonly api = inject(ChatApi);

  protected readonly view = signal<View>('loading');
  protected readonly messages = signal<ChatMessage[]>([]);
  protected readonly text = signal('');
  protected readonly sending = signal(false);
  protected readonly deleting = signal(false);
  protected readonly errors = signal<string[]>([]);
  /** The provider is not set up: the page says where to do it. */
  protected readonly needsProvider = signal(false);

  protected readonly textMax = TEXT_MAX;
  protected readonly length = computed(() => this.text().trim().length);
  protected readonly tooLong = computed(() => this.length() > TEXT_MAX);
  protected readonly canSend = computed(
    () => !this.sending() && !this.deleting() && this.length() > 0 && !this.tooLong(),
  );
  private readonly deleteDialog = viewChild(ConfirmDialog);

  ngOnInit(): Promise<void> {
    return this.load();
  }

  protected async load(): Promise<void> {
    this.view.set('loading');
    try {
      const result = await this.api.list();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.messages.set(result.messages);
      this.view.set('ready');
    } catch {
      this.view.set('unreachable');
    }
  }

  protected async send(): Promise<void> {
    if (!this.canSend()) {
      return;
    }
    this.errors.set([]);
    this.needsProvider.set(false);
    this.sending.set(true);
    try {
      const result = await this.api.write(this.text());
      switch (result.kind) {
        case 'ok':
          this.messages.update((list) => [...list, ...result.messages]);
          this.text.set('');
          break;
        case 'invalid':
          this.errors.set(result.errors);
          break;
        case 'not_configured':
          this.errors.set([NOT_CONFIGURED]);
          this.needsProvider.set(true);
          break;
        case 'provider_problem':
          this.errors.set([
            result.retry_after === null
              ? result.message
              : `${result.message} Try again in ${result.retry_after} seconds.`,
          ]);
          break;
        case 'rate_limited':
          this.errors.set([TOO_MANY]);
          break;
        case 'forbidden':
          this.view.set('signed_out');
          break;
      }
    } catch {
      this.errors.set([FALLBACK]);
    } finally {
      this.sending.set(false);
    }
  }

  protected askToDelete(): void {
    this.deleteDialog()?.open();
  }

  /** The dialog was answered with "Delete conversation". */
  protected async deleteAll(): Promise<void> {
    if (this.deleting() || this.sending()) {
      return;
    }
    this.errors.set([]);
    this.deleting.set(true);
    try {
      const result = await this.api.clear();
      if (result.kind === 'forbidden') {
        this.view.set('signed_out');
        return;
      }
      this.messages.set([]);
    } catch {
      this.errors.set([DELETE_FAILED]);
    } finally {
      this.deleting.set(false);
    }
  }

  protected onInput(event: Event): void {
    this.text.set((event.target as HTMLTextAreaElement).value);
  }

  /** The title of the change card: the draft it led to, or nothing more than the changes. */
  protected whatChanged(message: ChatMessage): string {
    if (message.season_plan !== null) {
      return 'What changed in a new draft of the season';
    }
    if (message.plan !== null) {
      return 'What changed in a new draft of the week';
    }
    return 'What changed';
  }

  /** "Nov 9 – Nov 15": the week a draft is for, so the link names it. */
  protected week(monday: string): string {
    return weekRange(monday);
  }
}
