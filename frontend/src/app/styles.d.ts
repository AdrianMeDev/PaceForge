// Only what the stylesheet spec reads from Node; the app itself never runs in Node.
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf-8'): string;
  export function readdirSync(path: string): string[];
}
