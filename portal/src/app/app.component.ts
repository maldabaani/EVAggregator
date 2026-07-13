import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';

type Theme = 'light' | 'dark';

const THEME_STORAGE_KEY = 'evagg-portal-theme';
const SIDEBAR_STORAGE_KEY = 'evagg-portal-sidebar-collapsed';

const PAGE_TITLES: Array<{ prefix: string; title: string }> = [
  { prefix: '/dashboard', title: 'Dashboard' },
  { prefix: '/partners', title: 'Roaming Partners' },
  { prefix: '/tariffs', title: 'Tariffs' },
  { prefix: '/cost-dashboard', title: 'Cost Reports' },
  { prefix: '/commands', title: 'Commands' },
];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnInit {
  theme: Theme = 'light';
  sidebarCollapsed = false;
  pageTitle = 'Dashboard';

  constructor(private readonly router: Router) {}

  ngOnInit(): void {
    const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    this.theme = storedTheme === 'dark' ? 'dark' : 'light';
    this.applyTheme();

    this.sidebarCollapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';

    this.updatePageTitle(this.router.url);
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe((event) => {
      this.updatePageTitle((event as NavigationEnd).urlAfterRedirects);
    });
  }

  toggleTheme(): void {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem(THEME_STORAGE_KEY, this.theme);
    this.applyTheme();
  }

  toggleSidebar(): void {
    this.sidebarCollapsed = !this.sidebarCollapsed;
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(this.sidebarCollapsed));
  }

  private applyTheme(): void {
    document.documentElement.setAttribute('data-theme', this.theme);
  }

  private updatePageTitle(url: string): void {
    const match = PAGE_TITLES.find((entry) => url.startsWith(entry.prefix));
    this.pageTitle = match?.title ?? 'Dashboard';
  }
}
