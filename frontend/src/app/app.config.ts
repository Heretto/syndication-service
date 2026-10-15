import { ApplicationConfig } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';
import { hopAuthInterceptor } from '@heretto/hop-ui';

import { routes } from './app.routes';
import { notificationInterceptor } from './core/interceptors/notification.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideAnimations(),
    provideHttpClient(withXhr(), withInterceptors([hopAuthInterceptor, notificationInterceptor])),
  ],
};
