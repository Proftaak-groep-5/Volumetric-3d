'use client';

import { useState } from "react";

interface CreateForm {
    name: string;
    description: string;
    image_Url: string;
}

export default function CreatePage() {
    const [formData, setFormData] = useState<CreateForm>({
        name: '',
        description: '',
        image_Url: ''
    });

    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
    const [loading, setLoading] = useState(false);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const {name, value} = e.target;
        setFormData(prev => ({...prev, [name]: value}));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);

        console.log(formData)
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/museums/createMuseum`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(formData)
            });
            console.log(res)

            const data = await res.json();

            if (res.ok) {
                setMessage({type: 'success', text: 'Museum successfully created!'});

                //Form resetten
                setFormData({
                    name: '',
                    description: '',
                    image_Url: ''
                });
            } else {
                setMessage({type: 'error', text: data.message || 'Something went wrong'});
            }
        } catch
            (error) {
            setMessage({type: 'error', text: 'Connection error - is your backend running?'});
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
            <div className="w-full max-w-lg bg-gray-900 rounded-2xl shadow-2xl p-8 border border-gray-800">
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-bold text-white mb-2">Create a museum</h1>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6 text-black">
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Name</label>
                        <input
                            type="text"
                            name="name"
                            value={formData.name}
                            onChange={handleChange}
                            required
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500"
                        />
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Bio</label>
                        <textarea
                            name="description"
                            value={formData.description}
                            onChange={handleChange}
                            rows={3}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3  focus:outline-none focus:border-blue-500 resize-y"
                        />
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Avatar URL</label>
                        <input
                            type="url"
                            name="image_Url"
                            value={formData.image_Url}
                            onChange={handleChange}
                            placeholder="https://example.com/avatar.jpg"
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 font-semibold py-4 rounded-xl transition-all duration-200 mt-4"
                    >
                        {loading ? 'Creating Museum...' : 'Create Museum'}
                    </button>
                </form>

                {message && (
                    <div className={`mt-6 p-4 rounded-xl text-center font-medium ${
                        message.type === 'success'
                            ? 'bg-green-900/50 text-green-400 border border-green-800'
                            : 'bg-red-900/50 text-red-400 border border-red-800'
                    }`}>
                        {message.text}
                    </div>
                )}
            </div>
        </div>
    )
}