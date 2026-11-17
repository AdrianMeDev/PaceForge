import { Component, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthStore } from '../core/auth/auth-store';
import { ThemeStore } from '../core/theme/theme-store';
import { OnlineStatus } from '../core/network/online-status';
import { UpdateNotice } from '../core/update/update-notice';
import { Icon } from '../shared/icon';
import { moreGroups, tabItems, visibleGroups } from './navigation';

/**
 * Frame around every page that needs a signed-in user: the pages in groups on a sidebar (from 64rem
 * with labels, from 40rem as a rail of icons) and the page itself next to it. Below 40rem a bar at the
 * bottom holds the pages used every day, and "More" opens a sheet with the rest and "Sign out".
 * The sheet is a native modal `<dialog>`: the browser keeps the focus inside, closes it on Escape,
 * makes the page behind inert and puts the focus back on "More".
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon, UpdateNotice],
  templateUrl: './shell.html',
  styleUrl: './shell.css',
})
export class Shell {
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly theme = inject(ThemeStore);
  protected readonly online = inject(OnlineStatus).online;

  protected readonly isStaff = this.store.isStaff;
  protected readonly groups = computed(() => visibleGroups(this.isStaff()));
  protected readonly tabs = tabItems();
  protected readonly shownTheme = this.theme.shown;
  protected readonly more = computed(() => moreGroups(this.isStaff()));

  private readonly sheet = viewChild<ElementRef<HTMLDialogElement>>('sheet');
  protected readonly moreOpen = signal(false);

  constructor() {
    // A click on the dialog itself, not on what is in it, is a click on the backdrop. (Escape and
    // the close button are the way for the keyboard, so this is no template event.)
    effect((onCleanup) => {
      const sheet = this.sheet()?.nativeElement;
      if (sheet) {
        const onClick = (event: MouseEvent): void => {
          if (event.target === sheet) {
            this.closeMore();
          }
        };
        sheet.addEventListener('click', onClick);
        onCleanup(() => sheet.removeEventListener('click', onClick));
      }
    });
  }
  protected readonly userLabel = computed(() => {
    const user = this.store.user();
    return user ? user.display_name || user.email : '';
  });

  protected toggleTheme(): void {
    this.theme.toggle();
  }

  protected openMore(): void {
    const sheet = this.sheet()?.nativeElement;
    if (sheet && !sheet.open) {
      sheet.showModal();
      this.moreOpen.set(true);
    }
  }

  protected closeMore(): void {
    const sheet = this.sheet()?.nativeElement;
    if (sheet?.open) {
      sheet.close();
    }
  }

  /** The dialog closed, whichever way (Escape, a button, a link). */
  protected closed(): void {
    this.moreOpen.set(false);
  }

  protected async logout(): Promise<void> {
    this.closeMore();
    await this.store.logout();
    await this.router.navigateByUrl('/login');
  }
}
