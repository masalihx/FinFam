// Views of the side panel and the bottom tab bar.
import { ask } from "./ask.js";
import { check } from "./check.js";
import { home } from "./home.js";
import { me } from "./me.js";
import { more, postponed, setup, transactions } from "./money.js";
import { goals, upcoming } from "./plan.js";
import { add, settings } from "./setting.js";

export const TABS = [
  { id: "home", label: "Home", icon: "⌂" },
  { id: "upcoming", label: "Upcoming", icon: "⏱" },
  { id: "ask", label: "Ask", icon: "✦" },
  { id: "me", label: "Me", icon: "☺" },
  { id: "more", label: "More", icon: "≡", children: ["goals", "transactions", "check", "add", "postponed", "setup", "settings"] },
];

export const VIEWS = { home, ask, check, upcoming, goals, me, transactions, setup, postponed, more, add, settings };
