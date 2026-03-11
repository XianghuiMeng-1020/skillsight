import type { Metadata } from "next";
import "./globals.css";
import { ToastProvider } from "@/components/Toast";
import { AppProviders } from "@/components/AppProviders";
import { AssessmentWidgetProvider } from "@/lib/AssessmentWidgetContext";
import { FloatingAssessmentWidget } from "@/components/FloatingAssessmentWidget";

export const metadata: Metadata = {
  title: "SkillSight - HKU Skills-to-Jobs System",
  description: "Evidence-based skill assessment and career readiness platform",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <body>
        <AppProviders>
          <ToastProvider>
            <AssessmentWidgetProvider>
              {children}
              <FloatingAssessmentWidget />
            </AssessmentWidgetProvider>
          </ToastProvider>
        </AppProviders>
      </body>
    </html>
  );
}
