import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './auth/auth.guards';

export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in · FleetPulse',
    canActivate: [guestGuard],
    loadComponent: () => import('./auth/login-page').then((m) => m.LoginPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        title: 'Overview · FleetPulse',
        loadComponent: () => import('./fleet/fleet-page').then((m) => m.FleetPage),
      },
      {
        path: 'alerts',
        title: 'Alerts · FleetPulse',
        loadComponent: () => import('./alerts/alerts-page').then((m) => m.AlertsPage),
      },
      {
        path: 'vessels/:id',
        title: 'Vessel · FleetPulse',
        loadComponent: () => import('./vessels/vessel-detail-page').then((m) => m.VesselDetailPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
