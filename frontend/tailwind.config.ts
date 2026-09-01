import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,vue}"],
  theme: {
    extend: {
      colors: {
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
        navy: { DEFAULT: "#0D2942", deep: "#0A1F33" },
        ink: "#18354D",
        brand: { DEFAULT: "#36C2A4", soft: "#E6F7F2" },
        review: { DEFAULT: "#F2A65A", soft: "#FDF3E7" },
        mist: "#F5F8FB",
        boundary: "#DCE6ED",
        primarytext: "#172B3A",
        secondarytext: "#6E8190",
        danger: { DEFAULT: "#D65353", soft: "#FBEDED" },
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
      borderRadius: { lg: "10px", md: "8px" },
    },
  },
  plugins: [],
} satisfies Config;
