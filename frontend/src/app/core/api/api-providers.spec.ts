import { HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideApiClient } from './api-providers';

function setCsrfCookie(value: string | null): void {
  document.cookie =
    value === null
      ? 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
      : `csrftoken=${value}; path=/`;
}

describe('provideApiClient', () => {
  let http: HttpClient;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideApiClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
    setCsrfCookie(null);
  });

  it('copies the csrftoken cookie into X-CSRFToken on mutating requests', () => {
    setCsrfCookie('token-123');

    http.post('/api/things/', {}).subscribe();
    http.delete('/api/things/1/').subscribe();

    expect(
      backend.expectOne({ method: 'POST', url: '/api/things/' }).request.headers.get('X-CSRFToken'),
    ).toBe('token-123');
    expect(
      backend
        .expectOne({ method: 'DELETE', url: '/api/things/1/' })
        .request.headers.get('X-CSRFToken'),
    ).toBe('token-123');
  });

  it('does not add the header to GET requests', () => {
    setCsrfCookie('token-123');

    http.get('/api/things/').subscribe();

    expect(backend.expectOne('/api/things/').request.headers.has('X-CSRFToken')).toBe(false);
  });

  it('never sends the token to another origin', () => {
    setCsrfCookie('token-123');

    http.post('https://other.example.com/api', {}).subscribe();

    expect(
      backend.expectOne('https://other.example.com/api').request.headers.has('X-CSRFToken'),
    ).toBe(false);
  });

  it('sends API requests past the service worker', () => {
    http.post('/api/season/plans/generate/', {}).subscribe();
    http.get('/api/me/').subscribe();

    for (const url of ['/api/season/plans/generate/', '/api/me/']) {
      expect(backend.expectOne(url).request.headers.get('ngsw-bypass')).toBe('true');
    }
  });

  it('leaves other requests to the service worker', () => {
    http.get('/manifest.webmanifest').subscribe();
    http.get('/apiary.png').subscribe();

    expect(backend.expectOne('/manifest.webmanifest').request.headers.has('ngsw-bypass')).toBe(
      false,
    );
    expect(backend.expectOne('/apiary.png').request.headers.has('ngsw-bypass')).toBe(false);
  });
});
