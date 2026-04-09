//Simple page that uses museum component to display a list of items in the museum
import Image from "next/image";
import MumseumComponent from "@/components/museums/MuseumComponent";

export default function MuseumPage() {
    return (
        <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
            <main className="flex flex-1 w-full max-w-3xl flex-col items-center justify-between py-32 px-16 bg-white dark:bg-black sm:items-start">
                <Image
                    className="dark:invert"
                    src="/museum.svg"
                    alt="Museum logo"
                    width={100}
                    height={20}
                    priority
                />
                <div className="flex flex-col items-center gap-6 text-center sm:items-start sm:text-left">
                    <h1 className="max-w-xs text-3xl font-semibold leading-10 tracking-tight text-black dark:text-zinc-50">
                        Welcome to the Museum!
                    </h1>
                    <p className="max-w-md text-lg leading-8 text-zinc-600 dark:text-zinc-400">
                        Explore our collection of artifacts and exhibits.
                    </p>
                </div>
                <MumseumComponent />
            </main>
        </div>
    );
}