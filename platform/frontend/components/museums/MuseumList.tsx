import MuseumCard from './MuseumCard';
import Museum from './types';

interface Props {
    museums: Museum[];
}

export default function MuseumList({ museums }: Props) {
    if (museums.length === 0) {
        return (
            <p className="text-center text-gray-500 py-12 text-lg">
                No museums found. Try adjusting your search.
            </p>
        );
    }

    return (
        <ul className="space-y-4">
            {museums.map((museum) => (
                <MuseumCard key={museum.id} museum={museum} />
            ))}
        </ul>
    );
}