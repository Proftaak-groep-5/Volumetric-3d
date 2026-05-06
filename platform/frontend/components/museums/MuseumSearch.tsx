'use client';

interface Props {
    searchTerm: string;
    onSearchChange: (value: string) => void;
}

export default function MuseumSearch({ searchTerm, onSearchChange }: Props) {
    return (
        <input
            type="text"
            placeholder="Search museums..."
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full max-w-md px-5 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 text-lg"
        />
    );
}