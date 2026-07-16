import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { NotificationService } from '../services/notification.service';

export const notificationInterceptor: HttpInterceptorFn = (req, next) => {
  const notifications = inject(NotificationService);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      const message = _errorMessage(error);
      if (message) notifications.error(message);
      return throwError(() => error);
    }),
  );
};

function _errorMessage(error: HttpErrorResponse): string | null {
  if (error.status === 0) return 'Unable to connect to the server';
  if (error.status === 400) return error.error?.detail || error.error?.error || 'Invalid request';
  if (error.status === 401) return null; // handled by redirect
  if (error.status === 403) return 'You do not have permission to perform this action';
  if (error.status === 404) return 'Resource not found';
  if (error.status === 409) return error.error?.detail || 'A sync may already be running';
  if (error.status >= 500) return error.error?.detail || error.error?.error || 'Server error';
  return null;
}
