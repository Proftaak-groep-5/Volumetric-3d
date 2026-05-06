// components/Navbar.jsx
import Link from 'next/link';

export default function Navbar() {
    return (
        <nav className="bg-blue-600 text-white shadow-lg fixed top-0 left-0 right-0 z-50">
            <div className="max-w-100% px-3">
                <div className="h-16 flex items-center justify-between">

                    {/* Linker gedeelte - Logo + Menu items */}
                    <div className="flex items-center gap-10">
                        {/* Logo */}
                        <Link href="/" className="font-bold text-2xl tracking-tight">
                            VolCap
                        </Link>

                        {/* Menu items */}
                        <div className="flex items-center gap-8 text-sm font-medium">
                            <Link
                                href="/museum"
                                className="hover:text-blue-200 transition-colors duration-200"
                            >
                                Museum
                            </Link>
                            <Link
                                href="/recording"
                                className="hover:text-blue-200 transition-colors duration-200"
                            >
                                Recordings
                            </Link>
                        </div>
                    </div>

                    {/* Rechter gedeelte - My Page */}
                    <div>
                        <Link
                            href="/user"
                            className="flex items-center gap-2 text-sm font-medium hover:text-blue-200 transition-colors duration-200"
                        >
                            My Page
                        </Link>
                    </div>
                </div>
            </div>
        </nav>
    );
}