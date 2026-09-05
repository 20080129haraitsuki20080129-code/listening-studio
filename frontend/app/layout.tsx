import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Listening Studio",
  description: "Turn English text into listening practice material.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}
