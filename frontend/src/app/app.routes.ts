import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { adminGuard } from './core/guards/admin.guard';
import { ShellComponent } from './shell/shell.component';

export const routes: Routes = [
  // ── Unauthenticated auth pages ────────────────────────────────────────────
  {
    path: 'login',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopLoginComponent),
  },
  {
    path: 'forgot-password',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopForgotPasswordComponent),
  },
  {
    path: 'reset-password',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopResetPasswordComponent),
  },
  {
    path: 'auth/sso/complete',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopSSOCallbackComponent),
  },
  {
    path: 'invite/:token',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAcceptInvitationComponent),
  },

  // ── Authenticated app shell ───────────────────────────────────────────────
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
      },
      {
        path: 'syncs/new',
        loadComponent: () =>
          import('./features/syncs/sync-form.component').then(m => m.SyncFormComponent),
      },
      {
        path: 'syncs/:id/edit',
        loadComponent: () =>
          import('./features/syncs/sync-form.component').then(m => m.SyncFormComponent),
      },
      {
        path: 'syncs/:id',
        loadComponent: () =>
          import('./features/syncs/sync-detail.component').then(m => m.SyncDetailComponent),
      },
      {
        path: 'syncs',
        loadComponent: () =>
          import('./features/syncs/sync-list.component').then(m => m.SyncListComponent),
      },
      {
        path: 'runs',
        loadComponent: () =>
          import('./features/runs/run-list.component').then(m => m.RunListComponent),
      },
      {
        path: 'account',
        loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAccountComponent),
      },
      {
        path: 'admin',
        canActivate: [adminGuard],
        loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAdminComponent),
      },
      { path: '**', redirectTo: 'dashboard' },
    ],
  },
];
