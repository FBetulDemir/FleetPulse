import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Fleet · FleetPulse',
    loadComponent: () => import('./fleet/fleet-page').then((m) => m.FleetPage),
  },
  { path: '**', redirectTo: '' },
];
