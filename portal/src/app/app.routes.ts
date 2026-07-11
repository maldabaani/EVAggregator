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
];
