'use client';

import {useState, useEffect} from "react";
import Museum from "../../components/museums/types";
import MuseumSearch from "../../components/museums/MuseumSearch";
import MuseumList from "../../components/museums/MuseumList";
import Link from "next/link";


export default function MuseumPage() {
    const [museums, setMuseums] = useState<Museum[]>([]);
    const [filteredMuseums, setFilteredMuseums] = useState<Museum[]>([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);


    async function fetchMuseums() {
        try {
            setLoading(true);
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/museums/getAll`);
            if (!response.ok) {
                throw new Error(`Error fetching museums: ${response.statusText}`);
            }
            console.log(response)
            const data = await response.json();
            setMuseums(data);
            setFilteredMuseums(data);
            console.log(data);
        } catch (err: any) {
            setError(err.message || 'Unknown error');
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        fetchMuseums()
    }, []);

    useEffect(() => {
        const filtered = museums.filter(museum =>
            museum.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (museum.owner?.username && museum.owner?.username.toLowerCase().includes(searchTerm.toLowerCase()))
        );
        setFilteredMuseums(filtered);
    }, [searchTerm, museums]);

    if (loading) {
        return <p className="text-center text-gray-500 py-12 text-lg">Loading museums...</p>;
    }
    if (error) {
        return <p className="text-center text-red-500 py-12 text-lg">{error}</p>;
    }

    return (
        <div>
            Check browser console for museums data. This page is under construction.
            {/*<div className="max-w-5xl mx-auto px-6 py-10">*/}
            {/*    <h1 className="text-4xl font-bold text-gray-800 mb-2">All museums</h1>*/}
            {/*    <p className="text-gray-600 mb-10">Find museums in our collection</p>*/}

            {/*    /!*<MuseumSearch searchTerm={searchTerm} onSearchChange={setSearchTerm}/>*!/*/}

            {/*    /!*<MuseumList museums={filteredMuseums}/>*!/*/}

            {/*    <Link*/}
            {/*        href="/createMuseum"*/}
            {/*        className="bg-blue-600 hover:bg-blue-700 text-white font-semibold px-6 py-3 rounded-xl transition-all duration-200 px-3 flex items-center gap-2"*/}
            {/*    >*/}
            {/*        + Create a museum*/}
            {/*    </Link>*/}
            {/*</div>*/}
        </div>
    )
}


