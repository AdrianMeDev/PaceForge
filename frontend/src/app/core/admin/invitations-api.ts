import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { API_BASE } from '../api/api-providers';
import {
  CreateInvitationResult,
  Denied,
  Invitation,
  ListInvitationsResult,
  ResendInvitationResult,
  RevokeInvitationResult,
} from './invitations-models';

const URL = `${API_BASE}/admin/invitations/`;
const INVALID_FALLBACK = 'The request was not accepted.';

/** The answer to creating or resending: the invitation plus the link and the mail result. */
interface IssuedBody extends Invitation {
  invite_url: string;
  email_sent: boolean;
}

interface Reply {
  status: number;
  body: unknown;
}

/**
 * The admin API for invitations. Refusals and validation problems that people can act on are
 * values; anything unexpected (network, 5xx) rejects.
 */
@Injectable({ providedIn: 'root' })
export class InvitationsApi {
  private readonly http = inject(HttpClient);

  async list(): Promise<ListInvitationsResult> {
    const reply = await this.send(this.http.get<Invitation[]>(URL, { observe: 'response' }));
    switch (reply.status) {
      case 200:
        return { kind: 'ok', invitations: reply.body as Invitation[] };
      case 403:
        return denied(reply);
      default:
        throw unexpected(reply);
    }
  }

  async create(email: string): Promise<CreateInvitationResult> {
    const reply = await this.send(this.http.post(URL, { email }, { observe: 'response' }));
    switch (reply.status) {
      case 201: {
        const issued = issuedOf(reply.body as IssuedBody);
        return { kind: 'created', ...issued };
      }
      case 400:
        return { kind: 'invalid', errors: messagesOf(reply.body) };
      case 403:
        return denied(reply);
      case 429:
        return { kind: 'rate_limited' };
      default:
        throw unexpected(reply);
    }
  }

  /** Issues a new link for a pending or expired invitation and mails it again. */
  async resend(id: string): Promise<ResendInvitationResult> {
    const reply = await this.send(
      this.http.post(`${URL}${encodeURIComponent(id)}/resend/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200: {
        const issued = issuedOf(reply.body as IssuedBody);
        return { kind: 'resent', ...issued };
      }
      case 404:
        return { kind: 'not_found' };
      case 409:
        return { kind: 'conflict' };
      case 429:
        return { kind: 'rate_limited' };
      case 403:
        return denied(reply);
      default:
        throw unexpected(reply);
    }
  }

  /** Revoking an invitation that is already revoked is fine and answers with it again. */
  async revoke(id: string): Promise<RevokeInvitationResult> {
    const reply = await this.send(
      this.http.post(`${URL}${encodeURIComponent(id)}/revoke/`, {}, { observe: 'response' }),
    );
    switch (reply.status) {
      case 200:
        return { kind: 'revoked', invitation: reply.body as Invitation };
      case 404:
        return { kind: 'not_found' };
      case 409:
        return { kind: 'conflict' };
      case 403:
        return denied(reply);
      default:
        throw unexpected(reply);
    }
  }

  private async send(request: Observable<HttpResponse<unknown>>): Promise<Reply> {
    try {
      const response = await firstValueFrom(request);
      return { status: response.status, body: response.body };
    } catch (error) {
      if (error instanceof HttpErrorResponse && [400, 403, 404, 409, 429].includes(error.status)) {
        return { status: error.status, body: error.error };
      }
      throw error;
    }
  }
}

/** Splits the answer to creating or resending into the invitation and the parts around it. */
function issuedOf({ invite_url, email_sent, ...invitation }: IssuedBody) {
  return { invitation, inviteUrl: invite_url, emailSent: email_sent };
}

function denied(reply: Reply): Denied {
  const code = (reply.body as { code?: unknown } | null)?.code;
  return { kind: code === 'mfa_required' ? 'mfa_required' : 'forbidden' };
}

/** DRF reports field errors as `{"email": ["…"]}`; all messages are collected. */
function messagesOf(body: unknown): string[] {
  if (typeof body !== 'object' || body === null) {
    return [INVALID_FALLBACK];
  }
  const messages = Object.values(body)
    .flat()
    .filter((value): value is string => typeof value === 'string');
  return messages.length ? messages : [INVALID_FALLBACK];
}

function unexpected(reply: Reply): Error {
  return new Error(`Unexpected response with status ${reply.status}`);
}
