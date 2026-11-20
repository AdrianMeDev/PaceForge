import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { InvitationsApi } from '../../core/admin/invitations-api';
import {
  CreateInvitationResult,
  Invitation,
  InvitationDelivery,
  ListInvitationsResult,
  ResendInvitationResult,
  RevokeInvitationResult,
} from '../../core/admin/invitations-models';
import { dayOf, query, required, settle, typeInto } from '../../testing/dom';
import { InvitationsPage } from './invitations-page';

const LINK = 'http://localhost:4200/account/signup?invitation=SECRET-TOKEN&email=ann%40example.com';

function invitation(overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: 'inv-1',
    email: 'ann@example.com',
    status: 'pending',
    created_at: '2026-11-12T21:07:49Z',
    expires_at: '2026-11-19T21:07:49Z',
    sent_at: null,
    ...overrides,
  };
}

const PENDING = invitation();
const USED = invitation({ id: 'inv-2', email: 'bob@example.com', status: 'used' });
const REVOKED = invitation({ id: 'inv-3', email: 'cy@example.com', status: 'revoked' });
const EXPIRED = invitation({ id: 'inv-4', email: 'di@example.com', status: 'expired' });

function createApiStub() {
  return {
    list: vi.fn<() => Promise<ListInvitationsResult>>(),
    create: vi.fn<(email: string) => Promise<CreateInvitationResult>>(),
    resend: vi.fn<(id: string) => Promise<ResendInvitationResult>>(),
    revoke: vi.fn<(id: string) => Promise<RevokeInvitationResult>>(),
  };
}

/** Replaces only the clipboard: Angular forms read other parts of `navigator` as well. */
function setClipboard(value: Pick<Clipboard, 'writeText'> | undefined): void {
  Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
}

describe('InvitationsPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let fixture: ComponentFixture<InvitationsPage>;
  let page: HTMLElement;
  let writeText: ReturnType<typeof vi.fn<(text: string) => Promise<void>>>;

  async function setup(first: ListInvitationsResult = { kind: 'ok', invitations: [] }) {
    api = createApiStub();
    api.list.mockResolvedValue(first);
    writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    setClipboard({ writeText });
    TestBed.configureTestingModule({
      imports: [InvitationsPage],
      providers: [provideRouter([]), { provide: InvitationsApi, useValue: api }],
    });
    fixture = TestBed.createComponent(InvitationsPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  afterEach(() => Reflect.deleteProperty(navigator, 'clipboard'));

  const ok = (...invitations: Invitation[]): ListInvitationsResult => ({
    kind: 'ok',
    invitations,
  });

  function button(label: string): HTMLButtonElement {
    const match = Array.from(page.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').trim().includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(label: string): Promise<void> {
    button(label).click();
    await settle(fixture);
  }

  async function invite(email: string): Promise<void> {
    typeInto(page, '#email', email);
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  const created = (
    email = 'ann@example.com',
    delivery: InvitationDelivery = 'sent',
  ): CreateInvitationResult => ({
    kind: 'created',
    invitation: invitation({ email }),
    inviteUrl: LINK,
    delivery,
  });

  const rows = () => Array.from(page.querySelectorAll('tbody tr'));
  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent?.trim());

  describe('loading', () => {
    it('shows a loading note until the list arrives', () => {
      api = createApiStub();
      api.list.mockReturnValue(new Promise<never>(() => undefined));
      TestBed.configureTestingModule({
        imports: [InvitationsPage],
        providers: [provideRouter([]), { provide: InvitationsApi, useValue: api }],
      });
      fixture = TestBed.createComponent(InvitationsPage);
      fixture.detectChanges();

      expect(
        fixture.nativeElement.querySelector('[role="status"][aria-label="Loading"]'),
      ).toBeTruthy();
      expect(fixture.nativeElement.querySelector('form')).toBeNull();
    });

    it('says so when there are no invitations yet', async () => {
      await setup();

      expect(text()).toContain('No invitations yet.');
      expect(page.querySelector('table')).toBeNull();
    });

    it('lists the invitations with their status', async () => {
      await setup(ok(PENDING, USED, REVOKED, EXPIRED));

      expect(rows().map((r) => r.querySelector('td')?.textContent)).toEqual([
        'ann@example.com',
        'bob@example.com',
        'cy@example.com',
        'di@example.com',
      ]);
      expect(rows().map((r) => r.querySelector('.status')?.textContent?.trim())).toEqual([
        'Pending',
        'Used',
        'Revoked',
        'Expired',
      ]);
    });

    it('shows when it was created and when it expires', async () => {
      await setup(ok(PENDING));

      expect(rows()[0].textContent).toContain(dayOf(PENDING.created_at));
      expect(rows()[0].textContent).toContain(dayOf(PENDING.expires_at));
    });

    it('offers to try again when the list cannot be loaded, and then shows it', async () => {
      await setup();
      api.list.mockRejectedValueOnce(new Error('offline'));
      api.list.mockResolvedValueOnce(ok(PENDING));
      fixture = TestBed.createComponent(InvitationsPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['The invitations could not be loaded.']);
      expect(page.querySelector('form')).toBeNull();

      await click('Try again');

      expect(alerts()).toEqual([]);
      expect(rows()).toHaveLength(1);
    });

    it('points an administrator without two-factor authentication to the security page', async () => {
      await setup({ kind: 'mfa_required' });

      expect(text()).toContain('turn on two-factor authentication');
      expect(page.querySelector('a')?.getAttribute('href')).toBe('/settings/security');
      expect(page.querySelector('form')).toBeNull();
    });

    it('shows a plain refusal without a way forward', async () => {
      await setup({ kind: 'forbidden' });

      expect(text()).toContain('not allowed');
      expect(page.querySelector('a')).toBeNull();
      expect(page.querySelector('form')).toBeNull();
    });
  });

  describe('creating', () => {
    it.each(['', '   ', 'not-an-email', 'a@'])(
      'does not send the address "%s" to the server',
      async (value) => {
        await setup();

        await invite(value);

        expect(api.create).not.toHaveBeenCalled();
        expect(text()).toContain('Enter a valid email address.');
        expect(query(page, '#email').getAttribute('aria-invalid')).toBe('true');
      },
    );

    it('sends the trimmed address', async () => {
      await setup();
      api.create.mockResolvedValue(created());

      await invite('  ann@example.com ');

      expect(api.create).toHaveBeenCalledExactlyOnceWith('ann@example.com');
    });

    it('shows the link once, with the address, and clears the form', async () => {
      await setup();
      api.create.mockResolvedValue(created());

      await invite('ann@example.com');

      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
      expect(query<HTMLInputElement>(page, '#invite-link').readOnly).toBe(true);
      expect(text()).toContain('Invitation for ann@example.com');
      expect(text()).toContain('only now');
      expect(query<HTMLInputElement>(page, '#email').value).toBe('');
    });

    it('refreshes the list after creating', async () => {
      await setup();
      api.create.mockResolvedValue(created());
      api.list.mockResolvedValue(ok(PENDING));

      await invite('ann@example.com');

      expect(api.list).toHaveBeenCalledTimes(2);
      expect(rows()).toHaveLength(1);
    });

    it('keeps the link visible when only the refresh fails, and says so', async () => {
      await setup();
      api.create.mockResolvedValue(created());
      api.list.mockRejectedValue(new Error('offline'));

      await invite('ann@example.com');

      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
      expect(alerts()).toEqual(['The list could not be refreshed.']);
    });

    it('selects the whole link when the field gets focus', async () => {
      await setup();
      api.create.mockResolvedValue(created());
      await invite('ann@example.com');
      const field = query<HTMLInputElement>(page, '#invite-link');

      field.dispatchEvent(new Event('focus'));

      expect(field.selectionStart).toBe(0);
      expect(field.selectionEnd).toBe(LINK.length);
    });

    it('never puts the link into the list', async () => {
      await setup();
      api.create.mockResolvedValue(created());
      api.list.mockResolvedValue(ok(PENDING));

      await invite('ann@example.com');
      await click('Done');

      expect(text()).not.toContain('SECRET-TOKEN');
      expect(page.querySelector('#invite-link')).toBeNull();
    });

    it('forgets the link when it is dismissed', async () => {
      await setup();
      api.create.mockResolvedValue(created());
      await invite('ann@example.com');

      await click('Done');

      expect(page.querySelector('#invite-link')).toBeNull();
      expect(page.innerHTML).not.toContain('SECRET-TOKEN');
    });

    it('replaces the link when another invitation is created', async () => {
      await setup();
      api.create.mockResolvedValueOnce(created());
      await invite('ann@example.com');
      api.create.mockResolvedValueOnce({
        kind: 'created',
        invitation: invitation({ email: 'bob@example.com' }),
        inviteUrl: 'http://localhost:4200/account/signup?invitation=OTHER',
        delivery: 'sent',
      });

      await invite('bob@example.com');

      expect(query<HTMLInputElement>(page, '#invite-link').value).toContain('OTHER');
      expect(text()).toContain('Invitation for bob@example.com');
      expect(text()).not.toContain('Invitation for ann@example.com');
    });

    it('shows the messages of the server and keeps the typed address', async () => {
      await setup();
      api.create.mockResolvedValue({ kind: 'invalid', errors: ['Enter a valid email address.'] });

      await invite('ann@example.com');

      expect(alerts()).toEqual(['Enter a valid email address.']);
      expect(query<HTMLInputElement>(page, '#email').value).toBe('ann@example.com');
      expect(page.querySelector('#invite-link')).toBeNull();
    });

    it('shows a generic message when the request fails', async () => {
      await setup();
      api.create.mockRejectedValue(new Error('offline'));

      await invite('ann@example.com');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('asks to wait when too many invitation mails were sent and keeps the typed address', async () => {
      await setup();
      api.create.mockResolvedValue({ kind: 'rate_limited' });

      await invite('ann@example.com');

      expect(alerts()).toEqual([
        'Too many invitation emails were sent. Please wait a few minutes and try again.',
      ]);
      expect(query<HTMLInputElement>(page, '#email').value).toBe('ann@example.com');
      expect(page.querySelector('form')).not.toBeNull();
    });

    it('switches to the security hint when two-factor authentication is missing', async () => {
      await setup();
      api.create.mockResolvedValue({ kind: 'mfa_required' });

      await invite('ann@example.com');

      expect(text()).toContain('turn on two-factor authentication');
      expect(page.querySelector('form')).toBeNull();
    });

    it('disables the button while sending and ignores a second submit', async () => {
      await setup();
      let finish: (result: CreateInvitationResult) => void = () => undefined;
      api.create.mockReturnValue(new Promise((resolve) => (finish = resolve)));

      typeInto(page, '#email', 'ann@example.com');
      query(page, 'form').dispatchEvent(new Event('submit'));
      query(page, 'form').dispatchEvent(new Event('submit'));
      fixture.detectChanges();

      expect(button('Working').disabled).toBe(true);
      expect(api.create).toHaveBeenCalledTimes(1);
      finish(created());
      await settle(fixture);
      expect(button('Send invitation by email').disabled).toBe(false);
    });
  });

  describe('copying', () => {
    async function withLink() {
      await setup();
      api.create.mockResolvedValue(created());
      await invite('ann@example.com');
    }

    it('copies the link to the clipboard and says so', async () => {
      await withLink();

      await click('Copy link');

      expect(writeText).toHaveBeenCalledExactlyOnceWith(LINK);
      expect(text()).toContain('Copied.');
    });

    it('reports a clipboard that does not work and keeps the link selectable', async () => {
      await withLink();
      writeText.mockRejectedValue(new DOMException('denied', 'NotAllowedError'));

      await click('Copy link');

      expect(text()).toContain('Copying did not work');
      expect(text()).not.toContain('Copied.');
      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
    });

    it('reports a browser without a clipboard', async () => {
      await withLink();
      setClipboard(undefined);

      await click('Copy link');

      expect(text()).toContain('Copying did not work');
    });

    it('does not claim "Copied." for the next link', async () => {
      await withLink();
      await click('Copy link');
      api.create.mockResolvedValue(created('bob@example.com'));

      await invite('bob@example.com');

      expect(text()).not.toContain('Copied.');
    });
  });

  describe('revoking', () => {
    it('offers Revoke for pending invitations only', async () => {
      await setup(ok(PENDING, USED, REVOKED, EXPIRED));

      expect(
        rows().map((r) =>
          Array.from(r.querySelectorAll('button')).some((b) => b.textContent?.trim() === 'Revoke'),
        ),
      ).toEqual([true, false, false, false]);
    });

    it('asks before revoking, and nothing happens on cancel', async () => {
      await setup(ok(PENDING));

      await click('Revoke');
      expect(text()).toContain('Revoke this invitation?');
      expect(api.revoke).not.toHaveBeenCalled();
      await click('Cancel');

      expect(api.revoke).not.toHaveBeenCalled();
      expect(text()).not.toContain('Revoke this invitation?');
    });

    it('asks about one invitation at a time', async () => {
      await setup(ok(PENDING, invitation({ id: 'inv-9', email: 'zed@example.com' })));

      await click('Revoke');

      expect(page.querySelectorAll('.confirm')).toHaveLength(1);
      expect(rows()[0].querySelector('.confirm')).not.toBeNull();
      expect(rows()[1].querySelector('.confirm')).toBeNull();
    });

    it('revokes the confirmed invitation and refreshes the list', async () => {
      await setup(ok(PENDING));
      api.revoke.mockResolvedValue({
        kind: 'revoked',
        invitation: { ...PENDING, status: 'revoked' },
      });
      api.list.mockResolvedValue(ok({ ...PENDING, status: 'revoked' }));

      await click('Revoke');
      await click('Yes, revoke');

      expect(api.revoke).toHaveBeenCalledExactlyOnceWith('inv-1');
      expect(rows()[0].querySelector('.status')?.textContent?.trim()).toBe('Revoked');
      expect(rows()[0].querySelector('button')).toBeNull();
      expect(text()).not.toContain('Revoke this invitation?');
    });

    it('explains that a used invitation cannot be revoked and reloads', async () => {
      await setup(ok(PENDING));
      api.revoke.mockResolvedValue({ kind: 'conflict' });
      api.list.mockResolvedValue(ok({ ...PENDING, status: 'used' }));

      await click('Revoke');
      await click('Yes, revoke');

      expect(alerts()).toEqual(['The invitation for ann@example.com has been used already.']);
      expect(rows()[0].querySelector('.status')?.textContent?.trim()).toBe('Used');
    });

    it('explains that an invitation is gone and reloads', async () => {
      await setup(ok(PENDING));
      api.revoke.mockResolvedValue({ kind: 'not_found' });
      api.list.mockResolvedValue(ok());

      await click('Revoke');
      await click('Yes, revoke');

      expect(alerts()).toEqual(['The invitation for ann@example.com no longer exists.']);
      expect(text()).toContain('No invitations yet.');
    });

    it('shows a generic message when the request fails and leaves the list as it was', async () => {
      await setup(ok(PENDING));
      api.revoke.mockRejectedValue(new Error('offline'));

      await click('Revoke');
      await click('Yes, revoke');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(rows()).toHaveLength(1);
    });

    it('switches to the security hint when two-factor authentication is missing', async () => {
      await setup(ok(PENDING));
      api.revoke.mockResolvedValue({ kind: 'mfa_required' });

      await click('Revoke');
      await click('Yes, revoke');

      expect(text()).toContain('turn on two-factor authentication');
      expect(api.list).toHaveBeenCalledTimes(1);
    });

    it('keeps the link of a new invitation visible while another one is revoked', async () => {
      await setup(ok(PENDING));
      api.create.mockResolvedValue(created('bob@example.com'));
      await invite('bob@example.com');
      api.revoke.mockResolvedValue({
        kind: 'revoked',
        invitation: { ...PENDING, status: 'revoked' },
      });
      api.list.mockResolvedValue(ok({ ...PENDING, status: 'revoked' }));

      await click('Revoke');
      await click('Yes, revoke');

      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
    });
  });

  describe('email feedback', () => {
    it.each(['sent', 'console', 'failed'] as const)(
      'shows only the %s notice after create and keeps the link available',
      async (delivery) => {
        await setup();
        api.create.mockResolvedValue(created('ann@example.com', delivery));

        await invite('ann@example.com');

        const notices = page.querySelectorAll('[data-result]');
        expect(notices).toHaveLength(1);
        expect(notices[0].getAttribute('data-result')).toBe(delivery);
        const messages = {
          sent: 'The invitation email was sent to ann@example.com.',
          console:
            'No mail server is configured; the email was only written to the server log. Send the link yourself.',
          failed: 'The invitation email could not be delivered to ann@example.com.',
        };
        expect(notices[0].textContent?.replace(/\s+/g, ' ').trim()).toBe(messages[delivery]);
        expect(notices[0].getAttribute('role')).toBe(delivery === 'failed' ? 'alert' : 'status');
        expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
      },
    );

    it('says the email was sent and still shows the fallback link', async () => {
      await setup();
      api.create.mockResolvedValue(created());

      await invite('ann@example.com');

      expect(query(page, '[data-result="sent"]').textContent).toContain(
        'The invitation email was sent to ann@example.com.',
      );
      expect(page.querySelector('[data-result="failed"]')).toBeNull();
      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
    });

    it('says the delivery failed and still shows the link', async () => {
      await setup();
      api.create.mockResolvedValue(created('ann@example.com', 'failed'));

      await invite('ann@example.com');

      expect(alerts()).toEqual(['The invitation email could not be delivered to ann@example.com.']);
      expect(page.querySelector('[data-result="sent"]')).toBeNull();
      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
    });

    it('shows when an invitation was last sent, and that it was not', async () => {
      await setup(ok(invitation({ sent_at: '2026-11-13T08:30:00Z' }), USED));

      expect(text()).toContain('Last sent');
      expect(rows()[0].querySelector('.sent-at')?.textContent).toContain(
        dayOf('2026-11-13T08:30:00Z'),
      );
      expect(rows()[1].querySelector('.sent-at')?.textContent).toContain('Not sent');
    });
  });

  describe('expired invitations', () => {
    it('points out a single expired invitation', async () => {
      await setup(ok(PENDING, EXPIRED));

      expect(query(page, '#expired-notice').textContent).toContain('1 invitation has expired');
    });

    it('counts several expired invitations', async () => {
      await setup(ok(EXPIRED, invitation({ id: 'inv-5', status: 'expired' })));

      expect(query(page, '#expired-notice').textContent).toContain('2 invitations have expired');
    });

    it('shows no notice without expired invitations', async () => {
      await setup(ok(PENDING, USED, REVOKED));

      expect(page.querySelector('#expired-notice')).toBeNull();
    });
  });

  describe('resending', () => {
    const resent = (
      delivery: InvitationDelivery = 'sent',
      issued: Invitation = invitation({ id: 'inv-4', email: 'di@example.com' }),
    ): ResendInvitationResult => ({
      kind: 'resent',
      invitation: issued,
      inviteUrl: LINK,
      delivery,
    });

    it.each(['sent', 'console', 'failed'] as const)(
      'shows only the %s notice after resend and keeps the link available',
      async (delivery) => {
        await setup(ok(PENDING));
        api.resend.mockResolvedValue(resent(delivery, PENDING));

        await click('Resend');

        const notices = page.querySelectorAll('[data-result]');
        expect(notices).toHaveLength(1);
        expect(notices[0].getAttribute('data-result')).toBe(delivery);
        const messages = {
          sent: 'The invitation email was sent to ann@example.com.',
          console:
            'No mail server is configured; the email was only written to the server log. Send the link yourself.',
          failed: 'The invitation email could not be delivered to ann@example.com.',
        };
        expect(notices[0].textContent?.replace(/\s+/g, ' ').trim()).toBe(messages[delivery]);
        expect(notices[0].getAttribute('role')).toBe(delivery === 'failed' ? 'alert' : 'status');
        expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
      },
    );

    it('offers Resend on pending and expired rows only', async () => {
      await setup(ok(PENDING, USED, REVOKED, EXPIRED));

      expect(
        rows().map((r) =>
          Array.from(r.querySelectorAll('button')).map((b) => b.textContent?.trim()),
        ),
      ).toEqual([['Resend', 'Revoke'], [], [], ['Resend']]);
    });

    it('resends an expired invitation, shows the new link and refreshes the list', async () => {
      await setup(ok(EXPIRED));
      api.resend.mockResolvedValue(resent());
      api.list.mockResolvedValue(ok({ ...EXPIRED, status: 'pending' }));

      await click('Resend');

      expect(api.resend).toHaveBeenCalledExactlyOnceWith('inv-4');
      expect(query(page, '[data-result="sent"]').textContent).toContain('di@example.com');
      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
      expect(api.list).toHaveBeenCalledTimes(2);
      expect(rows()[0].querySelector('.status')?.textContent?.trim()).toBe('Pending');
    });

    it('resends a pending invitation and reports a failed delivery', async () => {
      await setup(ok(PENDING));
      api.resend.mockResolvedValue(resent('failed', PENDING));

      await click('Resend');

      expect(api.resend).toHaveBeenCalledExactlyOnceWith('inv-1');
      expect(alerts()).toEqual(['The invitation email could not be delivered to ann@example.com.']);
      expect(query<HTMLInputElement>(page, '#invite-link').value).toBe(LINK);
    });

    it('explains that a used or revoked invitation cannot be sent again and reloads', async () => {
      await setup(ok(PENDING));
      api.resend.mockResolvedValue({ kind: 'conflict' });
      api.list.mockResolvedValue(ok({ ...PENDING, status: 'used' }));

      await click('Resend');

      expect(alerts()).toEqual([
        'The invitation for ann@example.com has been used or revoked already.',
      ]);
      expect(rows()[0].querySelector('.status')?.textContent?.trim()).toBe('Used');
      expect(rows()[0].querySelector('button')).toBeNull();
    });

    it('explains that an invitation is gone and reloads', async () => {
      await setup(ok(PENDING));
      api.resend.mockResolvedValue({ kind: 'not_found' });
      api.list.mockResolvedValue(ok());

      await click('Resend');

      expect(alerts()).toEqual(['The invitation for ann@example.com no longer exists.']);
      expect(text()).toContain('No invitations yet.');
    });

    it('asks to wait when too many mails were sent', async () => {
      await setup(ok(PENDING));
      api.resend.mockResolvedValue({ kind: 'rate_limited' });

      await click('Resend');

      expect(alerts()).toEqual([
        'Too many invitation emails were sent. Please wait a few minutes and try again.',
      ]);
      expect(page.querySelector('#invite-link')).toBeNull();
    });

    it('shows a generic message when the request fails', async () => {
      await setup(ok(PENDING));
      api.resend.mockRejectedValue(new Error('offline'));

      await click('Resend');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(rows()).toHaveLength(1);
    });

    it('switches to the security hint when two-factor authentication is missing', async () => {
      await setup(ok(PENDING));
      api.resend.mockResolvedValue({ kind: 'mfa_required' });

      await click('Resend');

      expect(text()).toContain('turn on two-factor authentication');
    });

    it('ignores a second click while a resend is running', async () => {
      await setup(ok(PENDING));
      let finish: (result: ResendInvitationResult) => void = () => undefined;
      api.resend.mockReturnValue(new Promise((resolve) => (finish = resolve)));

      button('Resend').click();
      fixture.detectChanges();
      button('Resend').click();

      expect(button('Resend').disabled).toBe(true);
      expect(api.resend).toHaveBeenCalledTimes(1);
      finish({ kind: 'conflict' });
      await settle(fixture);
    });
  });
});
