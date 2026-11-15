// Views of the side panel and the bottom tab bar.
import { check } from "./check.js";
import { home } from "./home.js";

export const TABS = [
  { id: "home", label: "Home", icon: "⌂" },
  { id: "upcoming", label: "Upcoming", icon: "⏱" },
  { id: "ask", label: "Ask", icon: "✦" },
  { id: "me", label: "Me", icon: "☺" },
  { id: "more", label: "More", icon: "≡", children: ["goals", "transactions", "check", "add", "postponed", "setup", "settings"] },
];

export const VIEWS = { home, check };
