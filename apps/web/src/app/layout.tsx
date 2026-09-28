import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vantage | Market Intelligence",
  description: "Executive market intelligence workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}