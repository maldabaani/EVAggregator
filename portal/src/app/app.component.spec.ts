import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AppComponent } from './app.component';

describe('AppComponent', () => {
  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
    localStorage.clear();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('renders the router outlet inside the app shell', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('main.app-shell')).toBeTruthy();
  });

  it('renders a sidebar nav link for every main section', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const links = Array.from(compiled.querySelectorAll('.sidebar__label')).map((el) => el.textContent?.trim());
    expect(links).toEqual(['Dashboard', 'Partners', 'Tariffs', 'Cost Reports', 'Commands']);
  });

  it('defaults to light mode and toggles to dark on click', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    const toggle = fixture.nativeElement.querySelector('[data-testid="theme-toggle"]') as HTMLButtonElement;
    toggle.click();
    fixture.detectChanges();

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('evagg-portal-theme')).toBe('dark');
  });

  it('remembers a previously chosen dark theme across reloads', () => {
    localStorage.setItem('evagg-portal-theme', 'dark');
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('toggles the sidebar collapsed state and remembers it', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('.shell--collapsed')).toBeFalsy();

    const collapseButton = compiled.querySelector('.sidebar__collapse-toggle') as HTMLButtonElement;
    collapseButton.click();
    fixture.detectChanges();

    expect(compiled.querySelector('.shell--collapsed')).toBeTruthy();
    expect(localStorage.getItem('evagg-portal-sidebar-collapsed')).toBe('true');
  });
});
