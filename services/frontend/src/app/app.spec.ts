//services/frontend/src/app/app.spec.ts
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AppComponent } from './app';
import { IdToken } from './models/user.model';

describe('App', () => {
  let httpTesting: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpTesting.verify());

  it('should create the app', async () => {
    const fixture = TestBed.createComponent(AppComponent);
    await fixture.whenStable();
    httpTesting.expectOne('/api/me');
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render the toolbar title', async () => {
    const fixture = TestBed.createComponent(AppComponent);
    await fixture.whenStable();
    httpTesting.expectOne('/api/me');
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('mat-toolbar')?.textContent).toContain('Secure File Gateway');
  });

  it('should offer sign in until the profile loads', async () => {
    const fixture = TestBed.createComponent(AppComponent);
    await fixture.whenStable();
    httpTesting.expectOne('/api/me');
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('mat-toolbar a')?.textContent).toContain('Sign In');
  });

  it('should show the username once /api/me responds', async () => {
    const user: IdToken = {
      name: 'Smoke Test',
      given_name: 'Smoke',
      family_name: 'Test',
      preferred_username: 'smoke-test',
      email: 'smoke-test@example.com',
      email_verified: true,
    };
    const fixture = TestBed.createComponent(AppComponent);
    await fixture.whenStable();
    httpTesting.expectOne('/api/me').flush({ id_token: user });
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.user-chip .username')?.textContent).toContain('smoke-test');
    expect(compiled.textContent).not.toContain('Sign In');
  });
});
