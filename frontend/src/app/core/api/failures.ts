import { HttpErrorResponse } from '@angular/common/http';

/** The server answered, but with a status or a body the page does not know what to do with. */
export class UnexpectedReplyError extends Error {
  constructor(
    readonly status: number,
    message = `Unexpected response with status ${status}`,
  ) {
    super(message);
    this.name = 'UnexpectedReplyError';
  }
}

const NO_ANSWER =
  'The server did not answer (the connection was closed or timed out). Reload the page to see ' +
  'whether anything was saved before you try again.';
const SOMETHING_WRONG = 'Something went wrong. Please try again.';

/**
 * The text for a request that failed in a way the page has no case for, with the HTTP status so
 * that the reason can be found (in the network tab or the server log). The error itself goes to
 * the browser console: it holds no key and no answer of the coach, only what the request was.
 */
export function describeFailure(error: unknown): string {
  console.error('A request of PaceForge failed:', error);
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) {
      return NO_ANSWER;
    }
    if (error.status === 502 || error.status === 504) {
      return (
        `The server gave up waiting (HTTP ${error.status}). Reload the page to see whether ` +
        'anything was saved before you try again.'
      );
    }
    return `Something went wrong on the server (HTTP ${error.status}). Please try again.`;
  }
  if (error instanceof UnexpectedReplyError) {
    return (
      `The server sent an answer this page cannot read (HTTP ${error.status}). Reload the page ` +
      'to see whether anything was saved.'
    );
  }
  return SOMETHING_WRONG;
}
