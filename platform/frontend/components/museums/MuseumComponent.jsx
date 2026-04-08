//Component to display all museums in the database included with a search engine.
import React, { useState, useEffect } from 'react';
import { getAllMuseums } from '../../services/museumService';
import MuseumCard from './MuseumCard';

const MuseumComponent = () => {
  const [museums, setMuseums] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchMuseums = async () => {
      const data = await getAllMuseums();
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
        {filteredMuseums.map(museum => (
          <MuseumCard key={museum.id} museum={museum} />
        ))}
      </div>
    </div>
  );
}