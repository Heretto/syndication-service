import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { HopAccountService } from '@heretto/hop-ui';
import { of } from 'rxjs';
import { map, switchMap, take } from 'rxjs/operators';

export const adminGuard: CanActivateFn = () => {
  const accountService = inject(HopAccountService);
  const router = inject(Router);
  return accountService.accountInfo$.pipe(
    take(1),
    switchMap(info => (info ? of(info) : accountService.getAccountInfo())),
    map(info => {
      if (info?.organization_role === 'admin' || info?.is_superuser) return true;
      router.navigate(['/dashboard']);
      return false;
    }),
  );
};
