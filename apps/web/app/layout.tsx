import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./academic.css";
import "./google.css";
import "./assistant.css";
import "./dashboard.css";
import "./design-system.css";
import "./planner.css";
import "./calm-dashboard.css";
export const metadata: Metadata = {
  title: "LifeOS — היום שלך, במקום אחד",
  description: "מרחב אישי מקומי לניהול משימות והיומן שלך",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "LifeOS",
    statusBarStyle: "black-translucent",
  },
  icons: { icon: "/icon.svg", apple: "/icon-192.png" },
};
export const viewport: Viewport = {
  themeColor: "#151719",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="he" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
