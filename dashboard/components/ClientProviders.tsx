'use client';

import { AuthProvider } from '@/lib/auth';
import AuthGuard from '@/components/AuthGuard';

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthGuard>{children}</AuthGuard>
    </AuthProvider>
  );
}
