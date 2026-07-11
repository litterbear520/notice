import "./globals.css";
import NavBar from "./components/NavBar";

export const metadata = { title: "模型公告聚合平台" };

// 首帧前同步设置主题，避免深色用户看到浅色闪烁
const themeInit = `(function(){try{var t=localStorage.getItem("theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
        <NavBar />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
