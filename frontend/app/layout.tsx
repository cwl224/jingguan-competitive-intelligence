import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ??
    requestHeaders.get("host") ??
    "localhost:3000";
  const protocol =
    requestHeaders.get("x-forwarded-proto") ??
    (host.startsWith("localhost") ? "http" : "https");
  const origin = `${protocol}://${host}`;

  return {
    metadataBase: new URL(origin),
    title: "镜观 · Agent 竞品分析",
    description: "覆盖采集、任务编排、数据清洗、证据追溯与知识存储的一体化竞品情报工作台",
    openGraph: {
      title: "镜观 · Agent 竞品分析工作台",
      description: "原始快照、版本链、结构化知识、证据追溯与专题集合的一体化竞品情报工作台",
      type: "website",
      url: origin,
      images: [
        {
          url: `${origin}/og-knowledge-storage.png`,
          width: 1731,
          height: 909,
          alt: "镜观数据与知识存储工作台",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "镜观 · Agent 竞品分析工作台",
      description: "原始快照、版本链、结构化知识、证据追溯与专题集合",
      images: [`${origin}/og-knowledge-storage.png`],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
