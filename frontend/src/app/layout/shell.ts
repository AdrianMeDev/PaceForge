import { Component, computed, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthStore } from '../core/auth/auth-store';
import { Icon } from '../shared/icon';
import { tabItems, visibleGroups } from './navigation';

/**
 * Frame around every page that needs a signed-in user: the pages in groups on a sidebar (from 64rem
 * with labels, from 40rem as a rail of icons) and the page itself next to it. Below 40rem a bar at the
 * bottom holds the pages used every day.
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon],
  templateUrl: './shell.html',
  styleUrl: './shell.css',
})
export class Shell {
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);

  protected readonly isStaff = this.store.isStaff;
  protected readonly groups = computed(() => visibleGroups(this.isStaff()));
  protected readonly tabs = tabItems();
  protected readonly userLabel = computed(() => {
    const user = this.store.user();
    return user ? user.display_name || user.email : '';
  });

  protected async logout(): Promise<void> {
    await this.store.logout();
    await this.router.navigateByUrl('/login');
  }
}
