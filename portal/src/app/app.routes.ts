import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  {
    path: 'dashboard',
    loadComponent: () => import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
  },
  {
    path: 'partners',
    loadComponent: () =>
      import('./features/partners/partner-list/partner-list.component').then((m) => m.PartnerListComponent),
  },
  {
    // Must come before 'partners/:id' — route matching is order-sensitive,
    // and :id would otherwise swallow the literal segment 'new' as if it
    // were a partner id.
    path: 'partners/new',
    loadComponent: () =>
      import('./features/partners/partner-create/partner-create.component').then((m) => m.PartnerCreateComponent),
  },
  {
    path: 'partners/:id',
    loadComponent: () =>
      import('./features/partners/partner-detail/partner-detail.component').then((m) => m.PartnerDetailComponent),
  },
  {
    path: 'tariffs',
    loadComponent: () =>
      import('./features/tariffs/tariff-list/tariff-list.component').then((m) => m.TariffListComponent),
  },
  {
    path: 'tariffs/new',
    loadComponent: () =>
      import('./features/tariffs/tariff-builder/tariff-builder.component').then((m) => m.TariffBuilderComponent),
  },
  {
    path: 'cost-dashboard',
    loadComponent: () =>
      import('./features/cost-dashboard/cost-dashboard.component').then((m) => m.CostDashboardComponent),
  },
  {
    path: 'commands',
    loadComponent: () =>
      import('./features/commands/command-panel/command-panel.component').then((m) => m.CommandPanelComponent),
  },
];
