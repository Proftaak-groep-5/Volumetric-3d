'use client';

import { useState } from 'react';

interface RegisterForm {
    email: string;
    username: string;
    password: string;
    repeatedPassword: string;
    first_name: string;
    last_name: string;
    bio: string;
    avatarUrl: string;
}

export default function TemporaryRegisterPage() {
    const [formData, setFormData] = useState<RegisterForm>({
        email: '',
        username: '',
        password: '',
        repeatedPassword: '',
        first_name: '',
        last_name: '',
        bio: '',
        avatarUrl: '',
    });

    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
    const [loading, setLoading] = useState(false);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);

        if (formData.password !== formData.repeatedPassword) {
            setMessage({ type: 'error', text: 'Passwords do not match!' });
            setLoading(false);
            return;
        }
        console.log(formData)
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/users/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });
            console.log(res)

            const data = await res.json();

            if (res.ok) {
                setMessage({ type: 'success', text: 'User successfully created!' });
                // Formulier resetten
                setFormData({
                    email: '', username: '', password: '', repeatedPassword: '',
                    first_name: '', last_name: '', bio: '', avatarUrl: ''
                });
            } else {
                setMessage({ type: 'error', text: data.message || 'Something went wrong' });
            }
        } catch (error) {
            setMessage({ type: 'error', text: 'Connection error - is your backend running?' });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
            <div className="w-full max-w-lg bg-gray-900 rounded-2xl shadow-2xl p-8 border border-gray-800">
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-bold text-white mb-2">Temporary Register</h1>
                    <p className="text-gray-400">Snel users toevoegen aan de database</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6 text-black">
                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Email</label>
                        <input
                            type="email"
                            name="email"
                            value={formData.email}
                            onChange={handleChange}
                            required
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500"
                        />
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Username</label>
                        <input
                            type="text"
                            name="username"
                            value={formData.username}
                            onChange={handleChange}
                            required
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500"
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-gray-400 mb-1">Password</label>
                            <input
                                type="password"
                                name="password"
                                value={formData.password}
                                onChange={handleChange}
                                required
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3  focus:outline-none focus:border-blue-500"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-gray-400 mb-1">Repeat Password</label>
                            <input
                                type="password"
                                name="repeatedPassword"
                                value={formData.repeatedPassword}
                                onChange={handleChange}
                                required
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-gray-400 mb-1">First Name</label>
                            <input
                                type="text"
                                name="first_name"
                                value={formData.first_name}
                                onChange={handleChange}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-gray-400 mb-1">Last Name</label>
                            <input
                                type="text"
                                name="last_name"
                                value={formData.last_name}
                                onChange={handleChange}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Bio</label>
                        <textarea
                            name="bio"
                            value={formData.bio}
                            onChange={handleChange}
                            rows={3}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3  focus:outline-none focus:border-blue-500 resize-y"
                        />
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-1">Avatar URL</label>
                        <input
                            type="url"
                            name="avatarUrl"
                            value={formData.avatarUrl}
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
                        {loading ? 'Creating User...' : 'Register User'}
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
    );
}