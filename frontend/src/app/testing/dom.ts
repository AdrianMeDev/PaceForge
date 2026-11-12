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
