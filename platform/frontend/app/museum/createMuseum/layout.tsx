// app/museum/createMuseum/layout.tsx
import type { Metadata } from 'next';
import { ReactNode } from 'react';

export const metadata: Metadata = {
    title: 'CreateMuseum',
};

export default function CreateMuseumLayout({ children }: { readonly children: ReactNode }) {
    return <div className="min-h-screen">{children}</div>;
}