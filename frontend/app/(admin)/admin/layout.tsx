/** Admin layout component with auth guard and responsive sidebar. */

"use client";

import React, { useEffect, useState, useCallback, useSyncExternalStore } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Sidebar } from "@/components/admin/Sidebar";
import { Header } from "@/components/admin/Header";
import { isAuthenticated } from "@/lib/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const isLoginPage = pathname === "/admin/login";
  const authedOnClient = useSyncExternalStore(
    () => () => {},
    () => isAuthenticated(),
    () => false
  );
  const checked = isLoginPage || authedOnClient;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastPathname, setLastPathname] = useState(pathname);

  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setSidebarOpen(false);
  }

  useEffect(() => {
    if (!isLoginPage && !authedOnClient) {
      router.replace("/admin/login");
    }
  }, [isLoginPage, authedOnClient, router]);

  const handleToggle = useCallback(() => setSidebarOpen((o) => !o), []);
  const handleClose = useCallback(() => setSidebarOpen(false), []);

  // Show nothing until auth check completes (avoids flash of admin content)
  if (!checked) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#EEEAE7]">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  // Login page has its own full-page layout — don't wrap with sidebar/header
  if (isLoginPage) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen bg-[#FAFAFA] overflow-hidden">
      {/* Mobile backdrop — closes sidebar when tapping outside */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 md:hidden"
          onClick={handleClose}
          aria-hidden="true"
        />
      )}

      <Sidebar isOpen={sidebarOpen} onClose={handleClose} />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <Header onSidebarToggle={handleToggle} />
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-4 md:p-6 bg-white">
          {children}
        </main>
      </div>
    </div>
  );
}
