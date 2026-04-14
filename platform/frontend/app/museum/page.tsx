'use client';

import React, { useState, useEffect } from "react";
import Museum from "../../components/museums/types";
import MuseumSearch from "../../components/museums/MuseumSearch";
import MuseumList from "../../components/museums/MuseumList";

export default function MuseumPage() {
    const [museums, setMuseums] = React.useState<Museum[]>([]);
    const [filteredMuseums, setFilteredMuseums] = React.useState<Museum[]>([]);
    const [searchTerm, setSearchTerm] = React.useState('');
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState<string | null>(null);

    useEffect(() => {
        async function fetchMuseums() {
            try {
                const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/getAll`);
                if (!response.ok) {
                    throw new Error(`Error fetching museums: ${response.statusText}`);
                }
                const data = await response.json();
                setMuseums(data);
                setFilteredMuseums(data);
            } catch (err: any) {
                setError(err.message || 'Unknown error');
            } finally {
                setLoading(false);
            }
        }
        fetchMuseums();
    }, []);

    useEffect(() => {
        const filtered = museums.filter(museum =>
            museum.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (museum.owner && museum.owner.toLowerCase().includes(searchTerm.toLowerCase()))
        );
        setFilteredMuseums(filtered);
    }, [searchTerm, museums]);

    if(loading) { return <p className="text-center text-gray-500 py-12 text-lg">Loading museums...</p>; }
    if(error) { return <p className="text-center text-red-500 py-12 text-lg">{error}</p>; }

    return (
        <div className="max-w-5xl mx-auto px-6 py-10">
            <h1 className="text-4xl font-bold text-gray-800 mb-2">All museums</h1>
            <p className="text-gray-600 mb-10">Find museums in our collection</p>

            <MuseumSearch searchTerm={searchTerm} onSearchChange={setSearchTerm} />

            <MuseumList museums={filteredMuseums} />
        </div>
    )
}


