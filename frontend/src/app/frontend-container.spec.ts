import { readFileSync } from 'node:fs';

// `ng test` runs in the folder of the project.
const dockerfile = readFileSync('Dockerfile', 'utf-8');

/** The instructions of the Dockerfile, with their line continuations joined. */
const instructions = dockerfile
  .replace(/\\\r?\n\s*/g, ' ')
  .split('\n')
  .map((line) => line.trim())
  .filter((line) => line !== '' && !line.startsWith('#'));

/** The commands of the RUN instructions, split at `&&`. */
const commands = instructions
  .filter((line) => /^RUN\s/.test(line))
  .flatMap((line) => line.replace(/^RUN\s+/, '').split('&&'))
  .map((command) => command.trim());

/** The owner and the paths of each `chown`, for example `['root:root', '/srv']`. */
const chowns = commands
  .filter((command) => /^chown\s/.test(command))
  .map((command) =>
    command
      .split(/\s+/)
      .slice(1)
      .filter((arg) => !arg.startsWith('-')),
  );

/**
 * The static assets in /srv are served to the browser. The runtime user must not be able to
 * change them, so root owns them and only root can write to them.
 */
describe('the frontend container image', () => {
  it('runs the runtime container as the paceforge user', () => {
    const users = instructions.filter((line) => /^USER\s/.test(line));
    expect(users.at(-1)).toBe('USER paceforge');
  });

  it('does not hand /srv to the paceforge user', () => {
    const srvOwners = chowns.filter((paths) => paths.includes('/srv')).map(([owner]) => owner);
    expect(srvOwners).toEqual(['root:root']);
    expect(chowns).toContainEqual(['paceforge:paceforge', '/data', '/config']);
  });

  it('keeps /srv owned by root and read-only with 0755 directories and 0644 files', () => {
    expect(commands).toContain('find /srv -type d -exec chmod 0755 {} +');
    expect(commands).toContain('find /srv -type f -exec chmod 0644 {} +');
  });
});
