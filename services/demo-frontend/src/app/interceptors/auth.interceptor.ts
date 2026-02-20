// src/app/interceptors/auth.interceptor.ts
import { HttpInterceptorFn } from '@angular/common/http';
import { IS_EXTERNAL_UPLOAD } from '../services/upload.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  // Check if the request has the bypass token
  if (req.context.get(IS_EXTERNAL_UPLOAD)) {
    // Pass the request through EXACTLY as it is (no extra headers)
    return next(req);
  }

  // Otherwise, clone the request and add your standard API headers
  const authReq = req.clone({
    setHeaders: {
      Authorization: `Bearer ${localStorage.getItem('token')}`,
      'X-Requested-With': 'XMLHttpRequest'
    }
  });

  return next(authReq);
};