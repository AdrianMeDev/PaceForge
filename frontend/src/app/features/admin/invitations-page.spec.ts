import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { InvitationsApi } from '../../core/admin/invitations-api';
import {
  CreateInvitationResult,
  Invitation,
  ListInvitationsResult,
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

  const created = (email = 'ann@example.com'): CreateInvitationResult => ({
    kind: 'created',
    invitation: invitation({ email }),
    inviteUrl: LINK,
  });

  const rows = () => Array.from(page.querySelectorAll('tbody tr'));
  const text = () => page.textContent ?? '';
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((e) => e.textContent);

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
      expect(button('Create invitation').disabled).toBe(false);
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

      expect(rows().map((r) => r.querySelector('button') !== null)).toEqual([
        true,
        false,
        false,
        false,
      ]);
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
});
