import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import {
  ActivateTotpResult,
  DeactivateTotpResult,
  Me,
  ReauthenticateResult,
  RecoveryCodesResult,
  RegenerateRecoveryCodesResult,
  TotpStatus,
} from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { ADA, createAuthStoreStub } from '../../core/auth/testing/auth-store-stub';
import { QrCode } from '../../shared/qr-code';
import { query, required, settle, typeInto } from '../../testing/dom';
import { SecurityPage } from './security-page';

const URL = 'otpauth://totp/ada%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=PaceForge';
const INACTIVE: TotpStatus = { kind: 'inactive', secret: 'JBSWY3DPEHPK3PXP', totpUrl: URL };
const ACTIVE: TotpStatus = { kind: 'active', createdAt: 1794510610, lastUsedAt: null };
const CODES = Array.from({ length: 10 }, (_, i) => `1000000${i}`);
const ALL_SET = { codes: CODES, total: 10, unused: 10 };
const ALL_CODES = { kind: 'codes' as const, ...ALL_SET };
const SOME_CODES = { kind: 'codes' as const, codes: CODES.slice(0, 2), total: 10, unused: 2 };
const REAUTH = { kind: 'reauthentication_required' as const };

const MEMBER_ON: Me = { ...ADA, mfa_enabled: true };
const ADMIN_OFF: Me = { ...ADA, is_staff: true, mfa_setup_required: true };
const ADMIN_ON: Me = { ...ADA, is_staff: true, mfa_enabled: true };

function routeWith(params: Record<string, string> = {}) {
  return {
    provide: ActivatedRoute,
    useValue: { snapshot: { queryParamMap: convertToParamMap(params) } },
  };
}

function createApiStub() {
  return {
    getTotp: vi.fn<() => Promise<TotpStatus>>(),
    activateTotp: vi.fn<(code: string) => Promise<ActivateTotpResult>>(),
    deactivateTotp: vi.fn<() => Promise<DeactivateTotpResult>>(),
    getRecoveryCodes: vi.fn<() => Promise<RecoveryCodesResult>>(),
    regenerateRecoveryCodes: vi.fn<() => Promise<RegenerateRecoveryCodesResult>>(),
    reauthenticate: vi.fn<(password: string) => Promise<ReauthenticateResult>>(),
  };
}

describe('SecurityPage', () => {
  let api: ReturnType<typeof createApiStub>;
  let store: ReturnType<typeof createAuthStoreStub>;
  let fixture: ComponentFixture<SecurityPage>;
  let page: HTMLElement;

  async function setup(
    user: Me = ADA,
    status: TotpStatus = ACTIVE,
    params: Record<string, string> = {},
  ): Promise<void> {
    api = createApiStub();
    api.getTotp.mockResolvedValue(status);
    store = createAuthStoreStub();
    store.signIn(user);
    TestBed.configureTestingModule({
      imports: [SecurityPage],
      providers: [
        { provide: AuthApi, useValue: api },
        { provide: AuthStore, useValue: store },
        routeWith(params),
      ],
    });
    fixture = TestBed.createComponent(SecurityPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  function button(label: string): HTMLButtonElement {
    const match = Array.from(page.querySelectorAll('button')).find((b) =>
      (b.textContent ?? '').includes(label),
    );
    return required(match, `a button "${label}"`);
  }

  async function click(label: string): Promise<void> {
    button(label).click();
    await settle(fixture);
  }

  async function submitForm(): Promise<void> {
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  async function enterCode(code: string): Promise<void> {
    typeInto(page, '#code', code);
    await submitForm();
  }

  async function enterPassword(password: string): Promise<void> {
    typeInto(page, '#password', password);
    await submitForm();
  }

  /** Off → setup screen. */
  async function openSetup(): Promise<void> {
    api.getTotp.mockResolvedValueOnce(INACTIVE);
    await click('Set up two-factor authentication');
  }

  const text = () => (page.textContent ?? '').replace(/\s+/g, ' ').trim();
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((el) => (el.textContent ?? '').trim());
  const fieldErrors = () =>
    Array.from(page.querySelectorAll('.field-error')).map((el) => (el.textContent ?? '').trim());
  const hasButton = (label: string) =>
    Array.from(page.querySelectorAll('button')).some((b) => (b.textContent ?? '').includes(label));
  const shownCodes = () =>
    Array.from(page.querySelectorAll('[data-testid="recovery-codes"] li')).map((li) =>
      (li.textContent ?? '').trim(),
    );

  describe('when two-factor authentication is off', () => {
    it('says so and offers the setup, without asking the server anything', async () => {
      await setup();

      expect(text()).toContain('Two-factor authentication is off');
      expect(hasButton('Set up two-factor authentication')).toBe(true);
      expect(api.getTotp).not.toHaveBeenCalled();
    });

    it('tells administrators that they have to turn it on', async () => {
      await setup(ADMIN_OFF);

      expect(text()).toContain('Administrators have to turn it on');
    });

    it('does not mention that to members', async () => {
      await setup();

      expect(text()).not.toContain('Administrators have to');
    });

    it('shows the QR code and the key in groups once the setup is started', async () => {
      await setup();

      await openSetup();

      const qr = fixture.debugElement.query(By.directive(QrCode));
      expect((qr.componentInstance as QrCode).value()).toBe(URL);
      expect(query(page, '[data-testid="secret"]').textContent).toBe('JBSW Y3DP EHPK 3PXP');
      expect(page.querySelector('label[for="code"]')).not.toBeNull();
      expect(query<HTMLInputElement>(page, '#code').autocomplete).toBe('one-time-code');
    });

    it('goes straight to the status when the server says it is already on', async () => {
      await setup();
      api.getTotp.mockResolvedValue(ACTIVE);

      await click('Set up two-factor authentication');

      expect(text()).toContain('Two-factor authentication is on');
    });

    it('shows a message and stays when the setup data cannot be fetched', async () => {
      await setup();
      api.getTotp.mockRejectedValueOnce(new Error('network down'));

      await click('Set up two-factor authentication');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(hasButton('Set up two-factor authentication')).toBe(true);
    });

    it('goes back to the status when the setup is cancelled', async () => {
      await setup();
      await openSetup();

      await click('Cancel');

      expect(text()).toContain('Two-factor authentication is off');
      expect(page.querySelector('app-qr-code')).toBeNull();
    });
  });

  describe('the notice an administrator is sent here with', () => {
    it('explains why they were sent here', async () => {
      await setup(ADMIN_OFF, ACTIVE, { notice: 'mfa-required' });

      expect(query(page, '[role="status"]').textContent).toContain(
        'Administrators must turn on two-factor authentication before continuing.',
      );
    });

    it.each(['unknown', '<b>hi</b>', 'toString', '__proto__', ''])('ignores %j', async (key) => {
      await setup(ADMIN_OFF, ACTIVE, { notice: key });

      expect(page.querySelector('[role="status"]')).toBeNull();
      expect(page.querySelector('b')).toBeNull();
    });

    it('goes away once the setup is started', async () => {
      await setup(ADMIN_OFF, ACTIVE, { notice: 'mfa-required' });

      await openSetup();

      expect(page.querySelector('[role="status"]')).toBeNull();
    });
  });

  describe('turning it on', () => {
    it('does not call the server without a code', async () => {
      await setup();
      await openSetup();

      await enterCode('   ');

      expect(api.activateTotp).not.toHaveBeenCalled();
      expect(fieldErrors()).toEqual(['Enter the code from your app.']);
    });

    it('sends the code without spaces', async () => {
      await setup();
      await openSetup();
      api.activateTotp.mockResolvedValue({ kind: 'invalid', errors: [] });

      await enterCode('123 456');

      expect(api.activateTotp).toHaveBeenCalledExactlyOnceWith('123456');
    });

    it('explains a wrong code and stays on the setup', async () => {
      await setup();
      await openSetup();
      api.activateTotp.mockResolvedValue({
        kind: 'invalid',
        errors: [{ code: 'incorrect_code', message: 'raw', param: 'code' }],
      });

      await enterCode('000000');

      expect(fieldErrors()).toEqual([
        'That code is not correct. Check the code in your authenticator app and try again.',
      ]);
      expect(store.reloadUser).not.toHaveBeenCalled();
      expect(page.querySelector('app-qr-code')).not.toBeNull();
    });

    it('turns it on, refreshes the account and shows the recovery codes to save', async () => {
      await setup();
      await openSetup();
      api.activateTotp.mockResolvedValue({ kind: 'activated' });
      api.getRecoveryCodes.mockResolvedValue(ALL_CODES);

      await enterCode('123456');

      expect(api.activateTotp).toHaveBeenCalledExactlyOnceWith('123456');
      expect(store.reloadUser).toHaveBeenCalledTimes(1);
      expect(shownCodes()).toEqual(CODES);
      expect(text()).toContain('Save these recovery codes now');
      expect(button('I have saved them')).toBeDefined();
    });

    it('shows the status after the codes were saved', async () => {
      await setup();
      await openSetup();
      api.activateTotp.mockResolvedValue({ kind: 'activated' });
      api.getRecoveryCodes.mockResolvedValue(ALL_CODES);
      await enterCode('123456');

      await click('I have saved them');

      expect(text()).toContain('Two-factor authentication is on');
      expect(page.querySelector('[data-testid="recovery-codes"]')).toBeNull();
    });

    describe('when the server wants the password again', () => {
      async function reachPrompt(): Promise<void> {
        await setup();
        await openSetup();
        api.activateTotp.mockResolvedValueOnce(REAUTH);
        await enterCode('123456');
      }

      it('asks for the password instead of failing', async () => {
        await reachPrompt();

        expect(text()).toContain('please confirm your password');
        expect(page.querySelector('label[for="password"]')).not.toBeNull();
        expect(page.querySelector('app-qr-code')).toBeNull();
      });

      it('repeats the activation with the same code after the password was confirmed', async () => {
        await reachPrompt();
        api.reauthenticate.mockResolvedValue({ kind: 'confirmed' });
        api.activateTotp.mockResolvedValue({ kind: 'activated' });
        api.getRecoveryCodes.mockResolvedValue(ALL_CODES);

        await enterPassword('correct-horse');

        expect(api.reauthenticate).toHaveBeenCalledExactlyOnceWith('correct-horse');
        expect(api.activateTotp).toHaveBeenCalledTimes(2);
        expect(api.activateTotp).toHaveBeenLastCalledWith('123456');
        expect(shownCodes()).toEqual(CODES);
      });

      it('does not repeat anything after a wrong password', async () => {
        await reachPrompt();
        api.reauthenticate.mockResolvedValue({
          kind: 'invalid',
          errors: [{ code: 'incorrect_password', message: 'raw', param: 'password' }],
        });

        await enterPassword('wrong');

        expect(fieldErrors()).toEqual(['That password is not correct.']);
        expect(api.activateTotp).toHaveBeenCalledTimes(1);
      });

      it('asks to wait when the rate limit applies', async () => {
        await reachPrompt();
        api.reauthenticate.mockResolvedValue({ kind: 'rate_limited' });

        await enterPassword('whatever');

        expect(fieldErrors()).toEqual(['Too many attempts. Please wait a minute and try again.']);
      });

      it('does not call the server for an empty password', async () => {
        await reachPrompt();

        await enterPassword('');

        expect(api.reauthenticate).not.toHaveBeenCalled();
        expect(fieldErrors()).toEqual(['Enter your password.']);
      });

      it('returns to the setup with the code kept when cancelled', async () => {
        await reachPrompt();

        await click('Cancel');

        expect(page.querySelector('app-qr-code')).not.toBeNull();
        expect(query<HTMLInputElement>(page, '#code').value).toBe('123456');
      });
    });

    it('shows a generic message when turning it on fails unexpectedly', async () => {
      await setup();
      await openSetup();
      api.activateTotp.mockRejectedValue(new Error('boom'));

      await enterCode('123456');

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(button('Turn on').disabled).toBe(false);
    });

    it('ignores a second submit while the first one is running', async () => {
      await setup();
      await openSetup();
      let finish!: (result: ActivateTotpResult) => void;
      api.activateTotp.mockReturnValue(
        new Promise<ActivateTotpResult>((resolve) => (finish = resolve)),
      );

      await enterCode('123456');
      expect(button('Checking').disabled).toBe(true);
      await submitForm();

      expect(api.activateTotp).toHaveBeenCalledTimes(1);
      finish({ kind: 'invalid', errors: [] });
      await settle(fixture);
    });
  });

  describe('when it is on', () => {
    it('shows since when and, if known, when it was last used', async () => {
      await setup(MEMBER_ON);
      expect(text()).toMatch(/Two-factor authentication is on since \w{3} \d{1,2}, \d{4}\./);
      expect(text()).not.toContain('Last used');
    });

    it('shows the last use', async () => {
      await setup(MEMBER_ON, { kind: 'active', createdAt: 1794510610, lastUsedAt: 1794600000 });

      expect(text()).toMatch(/Last used \w{3} \d{1,2}, \d{4}/);
    });

    it('lets members turn it off', async () => {
      await setup(MEMBER_ON);

      expect(hasButton('Turn off')).toBe(true);
      expect(text()).not.toContain('Administrators have to keep');
    });

    it('does not let administrators turn it off and says why', async () => {
      await setup(ADMIN_ON);

      expect(hasButton('Turn off')).toBe(false);
      expect(text()).toContain('Administrators have to keep two-factor authentication turned on.');
    });

    it('offers to try again when the status cannot be loaded, then recovers', async () => {
      api = createApiStub();
      api.getTotp.mockRejectedValueOnce(new Error('network down')).mockResolvedValue(ACTIVE);
      store = createAuthStoreStub();
      store.signIn(MEMBER_ON);
      TestBed.configureTestingModule({
        imports: [SecurityPage],
        providers: [
          { provide: AuthApi, useValue: api },
          { provide: AuthStore, useValue: store },
          routeWith(),
        ],
      });
      fixture = TestBed.createComponent(SecurityPage);
      page = fixture.nativeElement as HTMLElement;
      await settle(fixture);
      expect(alerts()).toEqual(['We could not load your security settings.']);

      await click('Try again');

      expect(text()).toContain('Two-factor authentication is on');
    });

    describe('recovery codes', () => {
      it('lists the unused codes without asking to save them', async () => {
        await setup(MEMBER_ON);
        api.getRecoveryCodes.mockResolvedValue(SOME_CODES);

        await click('Show recovery codes');

        expect(shownCodes()).toEqual(CODES.slice(0, 2));
        expect(query(page, '[data-testid="code-count"]').textContent).toBe('2 of 10');
        expect(text()).not.toContain('Save these recovery codes now');
      });

      it('returns to the status with "Done"', async () => {
        await setup(MEMBER_ON);
        api.getRecoveryCodes.mockResolvedValue(SOME_CODES);
        await click('Show recovery codes');

        await click('Done');

        expect(text()).toContain('Two-factor authentication is on');
      });

      it('says so when there are none', async () => {
        await setup(MEMBER_ON);
        api.getRecoveryCodes.mockResolvedValue({ kind: 'none' });

        await click('Show recovery codes');

        expect(text()).toContain('You have no recovery codes.');
      });

      it('asks for the password first when the server wants it, then shows them', async () => {
        await setup(MEMBER_ON);
        api.getRecoveryCodes.mockResolvedValueOnce(REAUTH).mockResolvedValueOnce(SOME_CODES);
        api.reauthenticate.mockResolvedValue({ kind: 'confirmed' });

        await click('Show recovery codes');
        expect(page.querySelector('label[for="password"]')).not.toBeNull();
        await enterPassword('correct-horse');

        expect(api.getRecoveryCodes).toHaveBeenCalledTimes(2);
        expect(shownCodes()).toEqual(CODES.slice(0, 2));
      });

      it('does not create new codes before the user has confirmed', async () => {
        await setup(MEMBER_ON);

        await click('Generate new recovery codes');

        expect(api.regenerateRecoveryCodes).not.toHaveBeenCalled();
        expect(alerts()[0]).toContain('old codes stop working');
      });

      it('keeps the old codes when the confirmation is cancelled', async () => {
        await setup(MEMBER_ON);
        await click('Generate new recovery codes');

        await click('Cancel');

        expect(api.regenerateRecoveryCodes).not.toHaveBeenCalled();
        expect(hasButton('Show recovery codes')).toBe(true);
      });

      it('replaces the codes after the confirmation and asks to save the new ones', async () => {
        await setup(MEMBER_ON);
        api.regenerateRecoveryCodes.mockResolvedValue({ kind: 'regenerated', ...ALL_SET });
        await click('Generate new recovery codes');

        await click('Generate new codes');

        expect(api.regenerateRecoveryCodes).toHaveBeenCalledTimes(1);
        expect(shownCodes()).toEqual(CODES);
        expect(text()).toContain('Save these recovery codes now');
      });

      it('asks for the password first when generating new ones, then repeats', async () => {
        await setup(MEMBER_ON);
        api.regenerateRecoveryCodes
          .mockResolvedValueOnce(REAUTH)
          .mockResolvedValueOnce({ kind: 'regenerated', ...ALL_SET });
        api.reauthenticate.mockResolvedValue({ kind: 'confirmed' });
        await click('Generate new recovery codes');
        await click('Generate new codes');

        await enterPassword('correct-horse');

        expect(api.regenerateRecoveryCodes).toHaveBeenCalledTimes(2);
        expect(shownCodes()).toEqual(CODES);
      });
    });

    describe('turning it off', () => {
      it('warns before doing anything and can be cancelled', async () => {
        await setup(MEMBER_ON);

        await click('Turn off');
        expect(api.deactivateTotp).not.toHaveBeenCalled();
        expect(alerts()[0]).toContain('removes your authenticator and your recovery codes');
        await click('Cancel');

        expect(api.deactivateTotp).not.toHaveBeenCalled();
        expect(hasButton('Show recovery codes')).toBe(true);
      });

      it('turns it off, refreshes the account and says so', async () => {
        await setup(MEMBER_ON);
        api.deactivateTotp.mockResolvedValue({ kind: 'deactivated' });
        await click('Turn off');

        await click('Turn off');

        expect(api.deactivateTotp).toHaveBeenCalledTimes(1);
        expect(store.reloadUser).toHaveBeenCalledTimes(1);
        expect(query(page, '[role="status"]').textContent).toContain('is turned off');
        expect(text()).toContain('Two-factor authentication is off');
      });

      it('asks for the password first when the server wants it, then repeats', async () => {
        await setup(MEMBER_ON);
        api.deactivateTotp
          .mockResolvedValueOnce(REAUTH)
          .mockResolvedValueOnce({ kind: 'deactivated' });
        api.reauthenticate.mockResolvedValue({ kind: 'confirmed' });
        await click('Turn off');
        await click('Turn off');

        await enterPassword('correct-horse');

        expect(api.deactivateTotp).toHaveBeenCalledTimes(2);
        expect(text()).toContain('Two-factor authentication is off');
      });

      it('shows a generic message when it fails unexpectedly and stays on', async () => {
        await setup(MEMBER_ON);
        api.deactivateTotp.mockRejectedValue(new Error('boom'));
        await click('Turn off');

        await click('Turn off');

        expect(alerts()).toContain('Something went wrong. Please try again.');
        expect(store.reloadUser).not.toHaveBeenCalled();
      });
    });
  });
});
