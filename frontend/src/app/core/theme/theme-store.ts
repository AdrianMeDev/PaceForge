import { DOCUMENT } from '@angular/common';
import { Injectable, computed, inject, signal } from '@angular/core';

export type ThemeChoice = 'system' | 'light' | 'dark';

export const THEME_CHOICES: readonly ThemeChoice[] = ['system', 'light', 'dark'];

/** Where the choice is kept in the browser; it is a convenience, never needed. */
export const THEME_KEY = 'paceforge.theme';

/**
 * The look the user chose: the device's (`system`, the default), light or dark. It is kept in the
 * browser and shown as `data-theme` on the `<html>` element, which the stylesheet reads; `system`
 * has no attribute at all. Storage may be missing or blocked (private windows, blocked site data):
 * then the choice only lasts until the page is closed, and nothing fails.
 */
@Injectable({ providedIn: 'root' })
export class ThemeStore {
  private readonly root = inject(DOCUMENT).documentElement;

  readonly choice = signal<ThemeChoice>('system');

  private readonly deviceDark = signal(deviceIsDark());

  /** What is on the screen now: the choice, or the device's setting while none is chosen. */
  readonly shown = computed<'light' | 'dark'>(() => {
    const choice = this.choice();
    return choice === 'system' ? (this.deviceDark() ? 'dark' : 'light') : choice;
  });

  /** Reads the stored choice and shows it; called once when the app starts. */
  initialize(): void {
    this.choice.set(read());
    this.apply();
    this.deviceDark.set(deviceIsDark());
    // The device may change from light to dark by itself (at night) while the app is open.
    globalThis.matchMedia?.('(prefers-color-scheme: dark)')?.addEventListener('change', (event) => {
      this.deviceDark.set(event.matches);
    });
  }

  /** Switches to the opposite of what is shown now (from "system" too). */
  toggle(): void {
    this.set(this.shown() === 'dark' ? 'light' : 'dark');
  }

  set(choice: ThemeChoice): void {
    if (!THEME_CHOICES.includes(choice)) {
      return;
    }
    this.choice.set(choice);
    write(choice);
    this.apply();
  }

  private apply(): void {
    const choice = this.choice();
    if (choice === 'system') {
      this.root.removeAttribute('data-theme');
    } else {
      this.root.setAttribute('data-theme', choice);
    }
  }
}

function deviceIsDark(): boolean {
  return globalThis.matchMedia?.('(prefers-color-scheme: dark)')?.matches ?? false;
}

function read(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return THEME_CHOICES.find((choice) => choice === stored) ?? 'system';
  } catch {
    return 'system';
  }
}

function write(choice: ThemeChoice): void {
  try {
    if (choice === 'system') {
      localStorage.removeItem(THEME_KEY);
    } else {
      localStorage.setItem(THEME_KEY, choice);
    }
  } catch {
    // Blocked or full: the choice still holds for this visit.
  }
}
