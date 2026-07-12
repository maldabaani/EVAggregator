import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'partners' },
  {
    path: 'partners',
    loadComponent: () =>
      import('./features/partners/partner-list/partner-list.component').then((m) => m.PartnerListComponent),
  },
  {
    path: 'partners/:id',
    loadComponent: () =>
      import('./features/partners/partner-detail/partner-detail.component').then((m) => m.PartnerDetailComponent),
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
