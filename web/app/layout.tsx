import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { MobileNav, Sidebar } from "@/components/sidebar";
import { ThemeProvider, themeBootstrapScript } from "@/components/theme-provider";
import "./globals.css";

// Chirp is proprietary to X; Inter is the closest freely licensable match and
// carries the Latin/Cyrillic/Greek coverage this app needs.
const inter = Inter({
  subsets: ["latin", "latin-ext", "cyrillic", "greek"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "X Toxicity Detection",
  description:
    "Analyze any public X profile for toxic posts in 56 languages, with per-language calibrated scores.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body className={`${inter.variable} antialiased`}>
        <ThemeProvider>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-full focus:bg-brand focus:px-4 focus:py-2 focus:text-white"
          >
            Skip to content
          </a>
          <div id="main" className="mx-auto flex w-full max-w-[1265px] justify-center">
            <Sidebar />
            {children}
          </div>
          <MobileNav />
        </ThemeProvider>
      </body>
    </html>
  );
}
