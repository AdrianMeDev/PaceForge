import { HttpErrorResponse } from '@angular/common/http';
import { UnexpectedReplyError, describeFailure } from './failures';

describe('describeFailure', () => {
  let logged: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => logged.mockRestore());

  const failed = (status: number) =>
    new HttpErrorResponse({ status, url: '/api/season/plans/generate/' });

  it('says that the server did not answer when the connection broke off', () => {
    expect(describeFailure(failed(0))).toBe(
      'The server did not answer (the connection was closed or timed out). Reload the page to ' +
        'see whether anything was saved before you try again.',
    );
  });

  it.each([502, 504])('says that the server gave up waiting (HTTP %i)', (status) => {
    expect(describeFailure(failed(status))).toBe(
      `The server gave up waiting (HTTP ${status}). Reload the page to see whether anything ` +
        'was saved before you try again.',
    );
  });

  it('names the status of any other error answer', () => {
    expect(describeFailure(failed(500))).toBe(
      'Something went wrong on the server (HTTP 500). Please try again.',
    );
  });

  it('names the status of an answer the page cannot read', () => {
    expect(describeFailure(new UnexpectedReplyError(201))).toBe(
      'The server sent an answer this page cannot read (HTTP 201). Reload the page to see ' +
        'whether anything was saved.',
    );
  });

  it('falls back to a general text for anything else', () => {
    expect(describeFailure(new Error('offline'))).toBe('Something went wrong. Please try again.');
    expect(describeFailure('strange')).toBe('Something went wrong. Please try again.');
  });

  it('logs the error to the console', () => {
    const error = failed(500);

    describeFailure(error);

    expect(logged).toHaveBeenCalledWith('A request of PaceForge failed:', error);
  });

  it('keeps the status on an unexpected answer', () => {
    const error = new UnexpectedReplyError(418);

    expect(error.status).toBe(418);
    expect(error.message).toBe('Unexpected response with status 418');
    expect(error).toBeInstanceOf(Error);
  });
});
