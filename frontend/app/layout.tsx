import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Pointse | Monitoring Wilkerstat",
  description:
    "Monitoring progres editing titik bangunan terhadap batas Wilkerstat BPS.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="id" className="h-full antialiased">
      <body className="min-h-full bg-slate-50 text-slate-900">{children}</body>
    </html>
  );
}
