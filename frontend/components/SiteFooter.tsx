import Link from "next/link";
import { getTranslations } from "next-intl/server";

export async function SiteFooter() {
  const t = await getTranslations("Legal");

  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-5xl gap-6 px-6 py-6 text-sm text-muted">
        <Link href="/privacy" className="hover:text-foreground">
          {t("footerPrivacy")}
        </Link>
        <Link href="/terms" className="hover:text-foreground">
          {t("footerTerms")}
        </Link>
      </div>
    </footer>
  );
}
