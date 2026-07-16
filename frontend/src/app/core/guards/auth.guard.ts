import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { HopAuthService } from '@heretto/hop-ui';

function isSafeReturnUrl(url: string): boolean {
  try {
    const decoded = decodeURIComponent(url);
    return decoded.startsWith('/') && !decoded.startsWith('//') && !decoded.includes('://');
  } catch {
    return false;
  }
}

export const authGuard: CanActivateFn = (_route, state) => {
  const authService = inject(HopAuthService);
  const router = inject(Router);
  if (authService.isAuthenticated()) return true;
  const returnUrl = isSafeReturnUrl(state.url) ? state.url : '/dashboard';
  router.navigate(['/login'], { queryParams: { returnUrl } });
  return false;
};
