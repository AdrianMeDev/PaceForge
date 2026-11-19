import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ChatApi } from '../../core/chat/chat-api';
import {
  ChatMessage,
  ClearMessagesResult,
  ListMessagesResult,
  SendMessageResult,
} from '../../core/chat/chat-models';
import { query, settle } from '../../testing/dom';
import { ChatPage, TEXT_MAX } from './chat-page';

const ASKED: ChatMessage = {
  id: 'm1',
  role: 'user',
  text: 'Rain on <b>Saturday</b>',
  created_at: '2026-11-14T10:00:00Z',
  changes: [],
  plan: null,
};
const ANSWERED: ChatMessage = {
  id: 'm2',
  role: 'coach',
  text: 'Sunday then.',
  created_at: '2026-11-14T10:00:05Z',
  changes: ['Run on Sat (60 min) moved to Sun'],
  plan: { id: 'p1', week_start: '2026-11-09' },
};

describe('ChatPage', () => {
  // jsdom has no modal dialog: this is what the browser does that the question relies on.
  beforeAll(() => {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      if (this.hasAttribute('open')) {
        this.removeAttribute('open');
        this.dispatchEvent(new Event('close'));
      }
    };
  });

  let fixture: ComponentFixture<ChatPage>;
  let page: HTMLElement;
  let list: ReturnType<typeof vi.fn<() => Promise<ListMessagesResult>>>;
  let write: ReturnType<typeof vi.fn<(text: string) => Promise<SendMessageResult>>>;
  let clear: ReturnType<typeof vi.fn<() => Promise<ClearMessagesResult>>>;

  async function setup(first: Promise<ListMessagesResult> | ListMessagesResult = ok()) {
    list = vi.fn<() => Promise<ListMessagesResult>>().mockReturnValue(Promise.resolve(first));
    write = vi.fn<(text: string) => Promise<SendMessageResult>>();
    clear = vi.fn<() => Promise<ClearMessagesResult>>();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: ChatApi, useValue: { list, write, clear } }],
    });
    fixture = TestBed.createComponent(ChatPage);
    page = fixture.nativeElement;
    await settle(fixture);
  }

  const ok = (...messages: ChatMessage[]): ListMessagesResult => ({ kind: 'ok', messages });
  const box = () => query<HTMLTextAreaElement>(page, '#chat-text');
  const sendButton = () => query<HTMLButtonElement>(page, '[data-testid="send"]');
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) =>
      e.textContent?.replace(/\s+/g, ' ').trim(),
    );

  function typeText(value: string): void {
    box().value = value;
    box().dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  async function press(): Promise<void> {
    sendButton().click();
    await settle(fixture);
  }

  describe('loading', () => {
    it('shows skeletons while the conversation loads', async () => {
      TestBed.configureTestingModule({
        providers: [
          provideRouter([]),
          {
            provide: ChatApi,
            useValue: { list: () => new Promise<never>(() => undefined) },
          },
        ],
      });
      fixture = TestBed.createComponent(ChatPage);
      fixture.detectChanges();

      expect(
        fixture.nativeElement.querySelector('[role="status"][aria-label="Loading"]'),
      ).toBeTruthy();
    });

    it('offers a retry when it cannot be loaded', async () => {
      list = vi.fn<() => Promise<ListMessagesResult>>();
      list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ok(ASKED));
      TestBed.configureTestingModule({
        providers: [provideRouter([]), { provide: ChatApi, useValue: { list } }],
      });
      fixture = TestBed.createComponent(ChatPage);
      page = fixture.nativeElement;
      await settle(fixture);
      expect(alerts()).toEqual(['Your conversation could not be loaded.']);

      query<HTMLButtonElement>(page, 'button.btn-primary').click();
      await settle(fixture);

      expect(alerts()).toEqual([]);
      expect(page.querySelectorAll('ol > li')).toHaveLength(1);
    });

    it('says when the session has ended', async () => {
      await setup({ kind: 'forbidden' });

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
      expect(page.querySelector('textarea')).toBeNull();
    });
  });

  describe('the conversation', () => {
    it('shows an empty state with examples when nothing was said', async () => {
      await setup(ok());

      expect(query(page, '[data-testid="empty"]').textContent).toContain('Tuesday I have no time');
      expect(page.querySelector('[data-testid="delete-all"]')).toBeNull();
    });

    it('shows the messages in order, each with who wrote it, as text only', async () => {
      await setup(ok(ASKED, ANSWERED));

      const items = Array.from(page.querySelectorAll('ol > li'));
      expect(items.map((li) => li.getAttribute('data-role'))).toEqual(['user', 'coach']);
      expect(items[0].querySelector('[data-testid="text"]')?.textContent?.trim()).toBe(
        'Rain on <b>Saturday</b>',
      );
      expect(items[0].querySelector('b')).toBeNull();
      expect(items[0].textContent).toContain('You');
      expect(items[1].textContent).toContain('Your coach');
    });

    it('says what changed and links to the draft of that week', async () => {
      await setup(ok(ASKED, ANSWERED));

      const changes = query(page, '[data-testid="changes"]');
      expect(
        Array.from(changes.querySelectorAll('li')).map((li) => li.textContent?.trim()),
      ).toEqual(['Run on Sat (60 min) moved to Sun']);
      expect(changes.textContent).toContain('Nothing is confirmed or sent');
      expect(query(changes, '[data-testid="open-draft"]').getAttribute('href')).toBe(
        '/planning?week=2026-11-09',
      );
    });

    it('lists changes even when there is no draft', async () => {
      await setup(
        ok(ASKED, {
          ...ANSWERED,
          changes: ['Illness noted as an absence (2026-11-14 to 2026-11-16)'],
          plan: null,
        }),
      );

      const changes = query(page, '[data-testid="changes"]');
      expect(
        Array.from(changes.querySelectorAll('li')).map((li) => li.textContent?.trim()),
      ).toEqual(['Illness noted as an absence (2026-11-14 to 2026-11-16)']);
      expect(changes.querySelector('[data-testid="open-draft"]')).toBeNull();
    });

    it('shows no change card for an answer that changed nothing', async () => {
      await setup(ok(ASKED, { ...ANSWERED, changes: [], plan: null }));

      expect(page.querySelector('[data-testid="changes"]')).toBeNull();
    });
  });

  describe('sending', () => {
    it('cannot send nothing', async () => {
      await setup();

      expect(sendButton().disabled).toBe(true);
      typeText('   ');
      expect(sendButton().disabled).toBe(true);
      expect(write).not.toHaveBeenCalled();
    });

    it('counts the characters and does not send a message that is too long', async () => {
      await setup();

      typeText('x'.repeat(TEXT_MAX + 1));

      expect(query(page, '[data-testid="count"]').textContent?.trim()).toBe(
        `${TEXT_MAX + 1} / ${TEXT_MAX}`,
      );
      expect(sendButton().disabled).toBe(true);
      expect(box().getAttribute('aria-invalid')).toBe('true');
    });

    it('sends the text, adds both messages and empties the box', async () => {
      await setup();
      write.mockResolvedValue({ kind: 'ok', messages: [ASKED, ANSWERED] });
      typeText('Rain on Saturday');

      await press();

      expect(write).toHaveBeenCalledExactlyOnceWith('Rain on Saturday');
      expect(page.querySelectorAll('ol > li')).toHaveLength(2);
      expect(box().value).toBe('');
      expect(page.querySelector('[data-testid="empty"]')).toBeNull();
    });

    it('says that the coach is thinking, and allows nothing else meanwhile', async () => {
      await setup(ok(ASKED));
      let finish: (result: SendMessageResult) => void = () => undefined;
      write.mockReturnValue(new Promise<SendMessageResult>((resolve) => (finish = resolve)));
      typeText('More');

      sendButton().click();
      fixture.detectChanges();

      expect(query(page, '[data-testid="thinking"]').textContent).toContain('a minute or two');
      expect(sendButton().disabled).toBe(true);
      expect(box().disabled).toBe(true);
      expect(query<HTMLButtonElement>(page, '[data-testid="delete-all"]').disabled).toBe(true);
      sendButton().click();
      expect(write).toHaveBeenCalledTimes(1);

      finish({ kind: 'ok', messages: [ASKED, ANSWERED] });
      await settle(fixture);
      expect(page.querySelector('[data-testid="thinking"]')).toBeNull();
    });

    it('keeps the text when the message cannot be used', async () => {
      await setup();
      write.mockResolvedValue({ kind: 'invalid', errors: ['Write a message.'] });
      typeText('Hello');

      await press();

      expect(alerts()).toEqual(['Write a message.']);
      expect(box().value).toBe('Hello');
    });

    it('points to the connections page when no provider is set up', async () => {
      await setup();
      write.mockResolvedValue({ kind: 'not_configured' });
      typeText('Hello');

      await press();

      expect(alerts()[0]).toContain('No AI provider is set up');
      expect(query(page, '[data-testid="connect"]').getAttribute('href')).toBe(
        '/settings/connections',
      );
      expect(box().value).toBe('Hello');
    });

    it('shows what the provider said, and when to try again', async () => {
      await setup();
      write.mockResolvedValue({
        kind: 'provider_problem',
        problem: 'rate_limited',
        message: 'The provider asks to slow down.',
        retry_after: 30,
      });
      typeText('Hello');

      await press();

      expect(alerts()).toEqual(['The provider asks to slow down. Try again in 30 seconds.']);
    });

    it('says when this server was asked too often', async () => {
      await setup();
      write.mockResolvedValue({ kind: 'rate_limited' });
      typeText('Hello');

      await press();

      expect(alerts()[0]).toContain('Too many messages');
    });

    it('shows a general message when the request fails, and can try again', async () => {
      await setup();
      write.mockRejectedValue(new Error('offline'));
      typeText('Hello');

      await press();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(sendButton().disabled).toBe(false);
    });

    it('shows the sign-in note when the session ended', async () => {
      await setup();
      write.mockResolvedValue({ kind: 'forbidden' });
      typeText('Hello');

      await press();

      expect(alerts()).toEqual(['Your session has ended. Please sign in again.']);
    });
  });

  describe('deleting the conversation', () => {
    const dialog = () => query<HTMLDialogElement>(page, '[data-testid="confirm-dialog"]');

    it('asks first and keeps everything on cancel', async () => {
      await setup(ok(ASKED, ANSWERED));

      query<HTMLButtonElement>(page, '[data-testid="delete-all"]').click();
      await settle(fixture);
      expect(dialog().open).toBe(true);
      expect(clear).not.toHaveBeenCalled();

      query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-cancel"]').click();
      await settle(fixture);

      expect(dialog().open).toBe(false);
      expect(clear).not.toHaveBeenCalled();
      expect(page.querySelectorAll('ol > li')).toHaveLength(2);
    });

    it('deletes it after the question and shows the empty state', async () => {
      await setup(ok(ASKED, ANSWERED));
      clear.mockResolvedValue({ kind: 'cleared' });

      query<HTMLButtonElement>(page, '[data-testid="delete-all"]').click();
      await settle(fixture);
      query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-confirm"]').click();
      await settle(fixture);

      expect(clear).toHaveBeenCalledTimes(1);
      expect(query(page, '[data-testid="empty"]')).toBeTruthy();
    });

    it('says so when deleting does not work and keeps the messages', async () => {
      await setup(ok(ASKED));
      clear.mockRejectedValue(new Error('offline'));

      query<HTMLButtonElement>(page, '[data-testid="delete-all"]').click();
      await settle(fixture);
      query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-confirm"]').click();
      await settle(fixture);

      expect(alerts()).toEqual(['The conversation could not be deleted. Please try again.']);
      expect(page.querySelectorAll('ol > li')).toHaveLength(1);
    });
  });
});
