import Image from "next/image";
import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-4">
        <Link href="/" className="flex items-center gap-3">
          <Image
            src="/app-icon-1024.png"
            alt=""
            width={36}
            height={36}
            className="rounded-lg"
          />
          <span className="text-sm font-semibold">Service ChatBot</span>
        </Link>
      </div>
    </header>
  );
}
