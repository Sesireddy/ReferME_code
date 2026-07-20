// Iter 73 — Central palette for bottom-nav icon colors.
//
// Applied consistently across ALL role tab layouts (student, professional, admin)
// so navigation icons feel cohesive and modern. Icons render in their assigned
// hue when active, and desaturated grey when inactive — mirroring the pattern
// used by LinkedIn / Naukri / Instagram.

import type { ComponentProps } from "react";
import type { Ionicons } from "@expo/vector-icons";

type IonName = ComponentProps<typeof Ionicons>["name"];

export type TabIconConfig = {
  name: IonName;
  activeColor: string;
};

// Route-name → (icon glyph, active hue) — pastel palette tuned for a light
// theme. Any tab route not listed here falls back to the neutral colors from
// tokens.ts.
export const TAB_ICON_MAP: Record<string, TabIconConfig> = {
  // Shared / cross-role
  dashboard:      { name: "home",                  activeColor: "#EF4444" }, // coral red
  jobs:           { name: "briefcase",             activeColor: "#3B82F6" }, // blue-500
  "mock-interviews": { name: "videocam",           activeColor: "#8B5CF6" }, // violet-500
  slots:          { name: "videocam",              activeColor: "#8B5CF6" },
  interviews:     { name: "videocam",              activeColor: "#8B5CF6" },
  leaderboard:    { name: "trophy",                activeColor: "#F59E0B" }, // amber-500
  profile:        { name: "person-circle",         activeColor: "#10B981" }, // emerald-500

  // Professional-only tabs
  "my-jobs":      { name: "folder-open",           activeColor: "#F97316" }, // orange-500
  "post-job":     { name: "add-circle",            activeColor: "#14B8A6" }, // teal-500

  // Admin-only tabs
  users:          { name: "people",                activeColor: "#EC4899" }, // pink-500
  transactions:   { name: "card",                  activeColor: "#059669" }, // emerald-600
  redemptions:    { name: "checkmark-done-circle", activeColor: "#0EA5E9" }, // sky-500
};

// Neutral grey used when the tab is not active — same for every role.
export const TAB_INACTIVE = "#94A3B8"; // slate-400
