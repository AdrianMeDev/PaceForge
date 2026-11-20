import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { DeleteAccountRequest, DeleteAccountResult, Me } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { ADA, createAuthStoreStub } from '../../core/auth/testing/auth-store-stub';
import { query, settle, typeInto } from '../../testing/dom';
import { DeleteAccountPanel } from './delete-account-panel';

const MEMBER_ON: Me = { ...ADA, mfa_enabled: true };

describe('DeleteAccountPanel', () => {
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

  let api: {
    deleteAccount: ReturnType<
      typeof vi.fn<(r: DeleteAccountRequest) => Promise<DeleteAccountResult>>
    >;
  };
  let store: ReturnType<typeof createAuthStoreStub>;
  let router: { navigate: ReturnType<typeof vi.fn> };
  let fixture: ComponentFixture<DeleteAccountPanel>;
  let page: HTMLElement;

  async function setup(user: Me = ADA): Promise<void> {
    api = { deleteAccount: vi.fn<(r: DeleteAccountRequest) => Promise<DeleteAccountResult>>() };
    store = createAuthStoreStub();
    store.signIn(user);
    router = { navigate: vi.fn().mockResolvedValue(true) };
    TestBed.configureTestingModule({
      imports: [DeleteAccountPanel],
      providers: [
        { provide: AuthApi, useValue: api },
        { provide: AuthStore, useValue: store },
        { provide: Router, useValue: router },
      ],
    });
    fixture = TestBed.createComponent(DeleteAccountPanel);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const dialog = () => query<HTMLDialogElement>(page, '[data-testid="confirm-dialog"]');
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((el) => (el.textContent ?? '').trim());
  const fieldErrors = () =>
    Array.from(page.querySelectorAll('.field-error')).map((el) => (el.textContent ?? '').trim());

  async function submit(): Promise<void> {
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  async function fill(email: string, password: string, code?: string): Promise<void> {
    typeInto(page, '#delete-confirmation', email);
    typeInto(page, '#delete-password', password);
    if (code !== undefined) {
      typeInto(page, '#delete-mfa-code', code);
    }
    await submit();
  }

  async function confirmDialog(): Promise<void> {
    query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-confirm"]').click();
    await settle(fixture);
  }

  it('warns that deletion is permanent and leaves Intervals.icu alone', async () => {
    await setup();

    const text = page.textContent ?? '';
    expect(query(page, 'h2').textContent).toBe('Delete account');
    expect(text).toContain('permanently');
    expect(text).toContain('Intervals.icu stay as they are');
  });

  it('asks for the email address and the password, and for no code without two-factor', async () => {
    await setup();

    expect(page.querySelector('#delete-confirmation')).not.toBeNull();
    expect(page.querySelector('#delete-password')).not.toBeNull();
    expect(page.querySelector('#delete-mfa-code')).toBeNull();
  });

  it('asks for a code when two-factor authentication is on', async () => {
    await setup(MEMBER_ON);

    expect(query<HTMLInputElement>(page, '#delete-mfa-code').autocomplete).toBe('one-time-code');
  });

  it('does not ask or call the server with empty fields', async () => {
    await setup();

    await submit();

    expect(fieldErrors()).toEqual(['Enter your email address to confirm.', 'Enter your password.']);
    expect(dialog().open).toBe(false);
    expect(api.deleteAccount).not.toHaveBeenCalled();
  });

  it('requires the code when two-factor authentication is on', async () => {
    await setup(MEMBER_ON);

    await fill('ada@example.com', 'secret', '  ');

    expect(fieldErrors()).toEqual(['Enter the code from your app.']);
    expect(dialog().open).toBe(false);
  });

  it('does not ask when the email address is not the one of the account', async () => {
    await setup();

    await fill('other@example.com', 'secret');

    expect(fieldErrors()).toEqual(['This is not the email address of your account.']);
    expect(dialog().open).toBe(false);
    expect(api.deleteAccount).not.toHaveBeenCalled();
  });

  it('asks a last question and sends nothing before it is answered', async () => {
    await setup();

    await fill('Ada@Example.com', 'secret');

    expect(dialog().open).toBe(true);
    expect(api.deleteAccount).not.toHaveBeenCalled();
  });

  it('keeps the account when the question is cancelled', async () => {
    await setup();
    await fill('ada@example.com', 'secret');

    query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-cancel"]').click();
    await settle(fixture);

    expect(dialog().open).toBe(false);
    expect(api.deleteAccount).not.toHaveBeenCalled();
  });

  it('deletes, forgets the session and goes to the login page', async () => {
    await setup();
    api.deleteAccount.mockResolvedValue({ kind: 'deleted' });
    await fill('ada@example.com', 'secret');

    await confirmDialog();

    expect(api.deleteAccount).toHaveBeenCalledExactlyOnceWith({
      confirmation: 'ada@example.com',
      password: 'secret',
      mfaCode: '',
    });
    expect(store.clearSession).toHaveBeenCalledTimes(1);
    expect(router.navigate).toHaveBeenCalledExactlyOnceWith(['/login'], {
      queryParams: { notice: 'account-deleted' },
    });
  });

  it('sends the code without spaces when two-factor authentication is on', async () => {
    await setup(MEMBER_ON);
    api.deleteAccount.mockResolvedValue({ kind: 'deleted' });
    await fill('ada@example.com', 'secret', '123 456');

    await confirmDialog();

    expect(api.deleteAccount).toHaveBeenCalledExactlyOnceWith({
      confirmation: 'ada@example.com',
      password: 'secret',
      mfaCode: '123456',
    });
  });

  it('shows the errors the server gives per field and stays signed in', async () => {
    await setup(MEMBER_ON);
    api.deleteAccount.mockResolvedValue({
      kind: 'invalid',
      errors: [
        { code: 'invalid', message: 'That password is not correct.', param: 'password' },
        { code: 'invalid', message: 'That code is not correct.', param: 'mfa_code' },
      ],
    });
    await fill('ada@example.com', 'wrong', '000000');

    await confirmDialog();

    expect(fieldErrors()).toEqual(['That password is not correct.', 'That code is not correct.']);
    expect(store.clearSession).not.toHaveBeenCalled();
    expect(router.navigate).not.toHaveBeenCalled();
  });

  it('shows a generic message for an invalid reply without a known field', async () => {
    await setup();
    api.deleteAccount.mockResolvedValue({ kind: 'invalid', errors: [] });
    await fill('ada@example.com', 'secret');

    await confirmDialog();

    expect(alerts()).toEqual(['Something went wrong. Please try again.']);
  });

  it('explains that the last administrator cannot delete the account', async () => {
    await setup();
    api.deleteAccount.mockResolvedValue({ kind: 'last_admin' });
    await fill('ada@example.com', 'secret');

    await confirmDialog();

    expect(alerts()[0]).toContain('only administrator');
    expect(store.clearSession).not.toHaveBeenCalled();
  });

  it('asks to wait when the rate limit applies', async () => {
    await setup();
    api.deleteAccount.mockResolvedValue({ kind: 'rate_limited' });
    await fill('ada@example.com', 'secret');

    await confirmDialog();

    expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);
  });

  it('says so when the user is signed out', async () => {
    await setup();
    api.deleteAccount.mockResolvedValue({ kind: 'forbidden' });
    await fill('ada@example.com', 'secret');

    await confirmDialog();

    expect(alerts()[0]).toContain('signed out');
  });

  it('shows a generic message when the request fails unexpectedly', async () => {
    await setup();
    api.deleteAccount.mockRejectedValue(new Error('boom'));
    await fill('ada@example.com', 'secret');

    await confirmDialog();

    expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    expect(query<HTMLButtonElement>(page, 'button[type="submit"]').disabled).toBe(false);
  });
});
