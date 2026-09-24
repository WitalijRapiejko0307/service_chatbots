import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

export default async function HomePage() {
  const t = await getTranslations("Marketing");

  const steps = [
    { title: t("step1Title"), body: t("step1Body") },
    { title: t("step2Title"), body: t("step2Body") },
    { title: t("step3Title"), body: t("step3Body") },
  ];

  const channels = [
    { title: t("telegramTitle"), body: t("telegramBody") },
    { title: t("viberTitle"), body: t("viberBody") },
    { title: t("instagramTitle"), body: t("instagramBody") },
    { title: t("tiktokTitle"), body: t("tiktokBody") },
  ];

  const reviewerItems = [
    { term: t("reviewerItem1Term"), desc: t("reviewerItem1Desc") },
    { term: t("reviewerItem2Term"), desc: t("reviewerItem2Desc") },
    { term: t("reviewerItem3Term"), desc: t("reviewerItem3Desc") },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-16 px-6 py-16">
        <section className="space-y-6">
          <h1 className="text-4xl font-semibold tracking-tight">{t("productName")}</h1>
          <p className="max-w-2xl text-lg text-muted">{t("heroLead")}</p>
          <div className="flex flex-wrap items-center gap-4">
            <Link
              href="/admin"
              className="inline-flex rounded-md bg-foreground px-4 py-2 text-sm font-medium text-surface hover:opacity-90"
            >
              {t("openAdmin")}
            </Link>
            <Link href="/privacy" className="text-sm text-muted hover:text-foreground">
              {t("privacyLink")}
            </Link>
          </div>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight">{t("howTitle")}</h2>
          <ol className="space-y-4">
            {steps.map((step, index) => (
              <li
                key={step.title}
                className="rounded-md border border-border bg-surface px-5 py-4"
              >
                <p className="text-sm font-medium text-muted">
                  {t("stepLabel", { number: index + 1 })}
                </p>
                <h3 className="mt-1 font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm text-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight">{t("channelsTitle")}</h2>
          <ul className="grid gap-4 sm:grid-cols-2">
            {channels.map((channel) => (
              <li
                key={channel.title}
                className="rounded-md border border-border px-5 py-4"
              >
                <h3 className="font-semibold">{channel.title}</h3>
                <p className="mt-2 text-sm text-muted">{channel.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight">{t("reviewerTitle")}</h2>
          <p className="max-w-2xl text-sm text-muted">{t("reviewerIntro")}</p>
          <dl className="divide-y divide-border rounded-md border border-border">
            {reviewerItems.map((item) => (
              <div key={item.term} className="px-5 py-4 sm:grid sm:grid-cols-[minmax(0,11rem)_1fr] sm:gap-4">
                <dt className="text-sm font-medium">{item.term}</dt>
                <dd className="mt-1 text-sm text-muted sm:mt-0">{item.desc}</dd>
              </div>
            ))}
          </dl>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
