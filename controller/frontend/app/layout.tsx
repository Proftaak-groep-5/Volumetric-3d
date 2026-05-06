import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
    title: "Volumetric Femto Controller",
    description: "Live multi-camera preview and volumetric point creation",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
    return (
        <html lang="en">
            <body>{children}</body>
        </html>
    );
}
