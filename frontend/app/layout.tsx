import "./globals.css";
import NavBar from "./components/NavBar";

export const metadata = { title: "模型公告聚合平台" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <NavBar />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
