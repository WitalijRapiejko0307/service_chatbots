import Link from "next/link";
import { SiteFooter } from "@/components/SiteFooter";

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-20">
        <h1 className="text-4xl font-semibold tracking-tight">Service ChatBot</h1>
        <p className="max-w-xl text-lg text-muted">
          Create an AI chatbot and connect it to messengers.
        </p>
        <p className="max-w-xl text-sm text-muted">
          For salons, clinics, schools, shops, and support teams. Telegram, Viber,
          Instagram, and TikTok — one inbox later in Admin.
        </p>
        <Link
          href="/admin"
          className="inline-flex w-fit rounded-md bg-foreground px-4 py-2 text-sm font-medium text-surface hover:opacity-90"
        >
          Open admin
        </Link>
      </main>
      <SiteFooter />
    </div>
  );
}
