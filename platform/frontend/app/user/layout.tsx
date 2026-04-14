// app/user/layout.tsx
import type { Metadata } from 'next';
import { ReactNode } from 'react';

export const metadata: Metadata = {
    title: 'User',
};

export default function UserLayout({ children }: { readonly children: ReactNode }) {
    return <div className="min-h-screen bg-gray-950">{children}</div>;
}