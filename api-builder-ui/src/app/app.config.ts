import { buttonFeedbackInterceptor } from './interceptors/button-feedback.interceptor';
import { localConnectionInterceptor } from './interceptors/local-connection.interceptor';
import { projectInterceptor } from './interceptors/project.interceptor';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, inject, provideAppInitializer } from '@angular/core';
import { provideRouter, withViewTransitions } from '@angular/router';
import { routes } from './app.routes';
import { authInterceptor } from './interceptors/auth.interceptor';
import { AuthService, LOCAL_PREVIEW } from './services/auth.service';

export const appConfig: ApplicationConfig = {
  providers: [
    // Anonymous cookie ownership is the current mode; no portal sign-in is needed.
    { provide: LOCAL_PREVIEW, useValue: true },
    provideHttpClient(withInterceptors([buttonFeedbackInterceptor, authInterceptor, projectInterceptor, localConnectionInterceptor])),
    provideAppInitializer(() => inject(AuthService).initialize()),
    provideRouter(
      routes,
      withViewTransitions({
        skipInitialTransition: true,
        onViewTransitionCreated: ({ transition }) => {
          if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
            transition.skipTransition();
          }
        },
      }),
    ),
  ],
};
