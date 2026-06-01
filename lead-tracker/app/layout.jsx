import "./globals.css";

export const metadata = {
  title: "Lead Tracker",
  description: "Sonoma / Bay Area web-design lead tracker",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
