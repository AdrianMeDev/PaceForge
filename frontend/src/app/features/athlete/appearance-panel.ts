import { Component, inject } from '@angular/core';
import { THEME_CHOICES, ThemeChoice, ThemeStore } from '../../core/theme/theme-store';

const LABELS: Record<ThemeChoice, string> = {
  system: 'Match my device',
  light: 'Light',
  dark: 'Dark',
};

/** The look of the app: the device's, light or dark. Applies at once and is kept in this browser. */
@Component({
  selector: 'app-appearance-panel',
  templateUrl: './appearance-panel.html',
  styleUrl: './appearance-panel.css',
})
export class AppearancePanel {
  private readonly theme = inject(ThemeStore);

  protected readonly choice = this.theme.choice;
  protected readonly choices = THEME_CHOICES.map((value) => ({ value, label: LABELS[value] }));

  protected choose(value: ThemeChoice): void {
    this.theme.set(value);
  }
}
