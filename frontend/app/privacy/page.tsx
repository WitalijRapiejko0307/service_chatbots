import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Legal");
  return {
    title: `${t("privacyTitle")} | ${t("productName")}`,
  };
}

export default async function PrivacyPage() {
  const t = await getTranslations("Legal");

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-20">
        <p className="text-sm text-muted">
          <Link href="/" className="hover:text-foreground">
            ← {t("backHome")}
          </Link>
        </p>
        <h1 className="mt-6 text-4xl font-semibold tracking-tight">{t("privacyTitle")}</h1>
        <p className="mt-2 text-sm text-muted">{t("lastUpdated")}</p>
        <p className="mt-6 max-w-2xl text-sm text-muted">{t("privacyDraft")}</p>

        <section className="mt-10 max-w-2xl space-y-3">
          <h2 className="text-xl font-semibold">{t("whoWeAreTitle")}</h2>
          <p className="text-muted">{t("whoWeAreBody")}</p>
        </section>
        <section className="mt-8 max-w-2xl space-y-3">
          <h2 className="text-xl font-semibold">{t("whoUsesTitle")}</h2>
          <p className="text-muted">{t("whoUsesBody")}</p>
        </section>
        <section className="mt-8 max-w-2xl space-y-3">
          <h2 className="text-xl font-semibold">{t("dataTitle")}</h2>
          <p className="text-muted">{t("dataBody")}</p>
        </section>
        <section className="mt-8 max-w-2xl space-y-3">
          <h2 className="text-xl font-semibold">{t("cookiesTitle")}</h2>
          <p className="text-muted">{t("cookiesBody")}</p>
        </section>
        <section className="mt-8 max-w-2xl space-y-3">
          <h2 className="text-xl font-semibold">{t("thirdPartiesTitle")}</h2>
          <p className="text-muted">{t("thirdPartiesBody")}</p>
        </section>
        <section className="mt-8 max-w-2xl space-y-3">
          <h2 className="text-xl font-semibold">{t("contactTitle")}</h2>
          <p className="text-muted">{t("contactBody")}</p>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
