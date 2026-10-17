import { Routes } from '@angular/router';
import {
  HopLoginComponent,
  HopForgotPasswordComponent,
  HopResetPasswordComponent,
  HopSSOCallbackComponent,
  HopAcceptInvitationComponent,
  HopAccountComponent,
  HopAdminComponent,
} from '@heretto/hop-ui';
import { authGuard } from './core/guards/auth.guard';
import { adminGuard } from './core/guards/admin.guard';
import { superadminGuard } from './core/guards/superadmin.guard';
import { ShellComponent } from './shell/shell.component';

export const routes: Routes = [
  // ── Unauthenticated auth pages ────────────────────────────────────────────
  {
    path: 'login',
    component: HopLoginComponent,
  },
  {
    path: 'forgot-password',
    component: HopForgotPasswordComponent,
  },
  {
    path: 'reset-password',
    component: HopResetPasswordComponent,
  },
  {
    path: 'auth/sso/complete',
    component: HopSSOCallbackComponent,
  },
  {
    path: 'invite/:token',
    component: HopAcceptInvitationComponent,
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
        component: HopAccountComponent,
      },
      {
        path: 'admin',
        canActivate: [adminGuard],
        component: HopAdminComponent,
      },
      {
        path: 'superadmin',
        canActivate: [superadminGuard],
        loadComponent: () =>
          import('./features/admin/superadmin.component').then(m => m.SuperadminComponent),
      },
      { path: '**', redirectTo: 'dashboard' },
    ],
  },
];
