// app/museum/layout.tsx
import type { Metadata } from 'next';
import { ReactNode } from 'react';

export const metadata: Metadata = {
    title: 'Museum',
};

export default function MuseumLayout({ children }: { readonly children: ReactNode }) {
    return <div className="min-h-screen">{children}</div>;
}