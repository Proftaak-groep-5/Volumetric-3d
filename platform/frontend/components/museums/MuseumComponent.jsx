//Component to display all museums in the database included with a search engine.
'use client';

import React, { useState, useEffect } from 'react';

export default function MuseumComponent() {
  const [museums, setMuseums] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchMuseums = async () => {
      const data = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/museums/getAll`).then(res => res.json());
      setMuseums(data);
    };
    fetchMuseums();
  }, []);

  const filteredMuseums = museums.filter(museum =>
    museum.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div>
      <h1>Museums</h1>
      <input
        type="text"
        placeholder="Search museums..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />
      <div className="museum-list">
        Something
      </div>
    </div>
  );
}