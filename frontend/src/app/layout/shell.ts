import { Component, computed, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthStore } from '../core/auth/auth-store';

/** Frame around every page that needs a signed-in user. */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './shell.html',
  styleUrl: './shell.css',
})
export class Shell {
  private readonly store = inject(AuthStore);
  private readonly router = inject(Router);

  protected readonly isStaff = this.store.isStaff;
  protected readonly userLabel = computed(() => {
    const user = this.store.user();
    return user ? user.display_name || user.email : '';
  });

  protected async logout(): Promise<void> {
    await this.store.logout();
    await this.router.navigateByUrl('/login');
  }
}
