import type { Config } from "tailwindcss";

/**
 * 深海权限台主题（原型设计说明 §6）
 * Deep Navy 侧栏 / Teal 主操作 / Amber 待审核 / Mist 页面背景
 * shadcn 语义 token 用 rgb 三元组变量，支持 /opacity 修饰符。
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ---- shadcn 语义 token（深海权限台映射）----
        background: "rgb(var(--background) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)",
        card: "rgb(var(--card) / <alpha-value>)",
        "card-foreground": "rgb(var(--card-foreground) / <alpha-value>)",
        popover: "rgb(var(--popover) / <alpha-value>)",
        "popover-foreground": "rgb(var(--popover-foreground) / <alpha-value>)",
        primary: "rgb(var(--primary) / <alpha-value>)",
        "primary-foreground": "rgb(var(--primary-foreground) / <alpha-value>)",
        secondary: "rgb(var(--secondary) / <alpha-value>)",
        "secondary-foreground": "rgb(var(--secondary-foreground) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        "muted-foreground": "rgb(var(--muted-foreground) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-foreground": "rgb(var(--accent-foreground) / <alpha-value>)",
        destructive: "rgb(var(--destructive) / <alpha-value>)",
        "destructive-foreground": "rgb(var(--destructive-foreground) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        input: "rgb(var(--input) / <alpha-value>)",
        ring: "rgb(var(--ring) / <alpha-value>)",
        // ---- 品牌直达色（自定义布局用）----
        navy: {
          DEFAULT: "#0D2942", // 侧栏、AI 工作台主背景
          deep: "#0A1F33",
        },
        ink: "#18354D", // 标题、关键图表
        brand: {
          DEFAULT: "#36C2A4", // Authorization Teal：已授权、成功、主操作
          soft: "#E6F7F2",
        },
        review: {
          DEFAULT: "#F2A65A", // Review Amber：待审核、风险、权限提醒
          soft: "#FDF3E7",
        },
        mist: "#F5F8FB", // 页面背景
        boundary: "#DCE6ED", // 表格、分隔、输入边界
        primarytext: "#172B3A", // 正文
        secondarytext: "#6E8190", // 辅助文字
        danger: {
          DEFAULT: "#D65353",
          soft: "#FBEDED",
        },
      },
      fontFamily: {
        display: ["Manrope", "Noto Sans SC", "system-ui", "sans-serif"],
        body: ["Noto Sans SC", "Manrope", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      keyframes: {
        "pulse-line": {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-line": "pulse-line 2.4s linear infinite",
        "fade-up": "fade-up 0.28s ease-out both",
      },
      borderRadius: {
        lg: "10px",
        md: "8px",
      },
    },
  },
  plugins: [],
} satisfies Config;
