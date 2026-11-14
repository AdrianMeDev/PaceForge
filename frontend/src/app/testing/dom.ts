import { ComponentFixture } from '@angular/core/testing';

/** Returns the first match or fails the test with a readable message (instead of `!`). */
export function query<T extends Element = HTMLElement>(root: ParentNode, selector: string): T {
  const element = root.querySelector<T>(selector);
  if (element === null) {
    throw new Error(`Expected an element matching "${selector}"`);
  }
  return element;
}

export function required<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`Expected ${what} to exist`);
  }
  return value;
}

/** Types into an input the way a user would, so that Angular forms see the change. */
export function typeInto(root: ParentNode, selector: string, value: string): void {
  const input = query<HTMLInputElement>(root, selector);
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

/** Lets pending promises of an async handler finish, then renders the result. */
export async function settle(fixture: ComponentFixture<unknown>): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve));
  await fixture.whenStable();
}

/**
 * The day of a timestamp the way the pages show it (`Nov 13, 2026`), in the time zone of the
 * machine, as the pages do. Worked out with `Intl` and not with Angular's pipe, so that the
 * expectation does not share its code with what is tested, and without fixing a zone: a literal
 * such as "Nov 13" is only right in some zones for a given time of day.
 */
export function dayOf(timestamp: string): string {
  return new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(new Date(timestamp));
}
