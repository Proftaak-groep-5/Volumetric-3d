import Museum from './types';

interface Props {
    museum: Museum;
}

export default function MuseumCard({ museum }: Props) {
    return (
        <li className="bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md transition-all duration-200">
            <div className="flex justify-between items-start">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-900">{museum.name}</h2>
                    {museum.owner && (
                        <p className="text-blue-600 mt-1 flex items-center gap-1">
                            {museum.owner?.username}
                        </p>
                    )}
                </div>
                    <span className="text-sm text-gray-500 bg-gray-100 px-3 py-1 rounded-full">
            View
          </span>
            </div>
        </li>
    );
}