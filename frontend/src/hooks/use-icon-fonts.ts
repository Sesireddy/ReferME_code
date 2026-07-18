// Icon font loader for Expo apps.
//
// Iter 70 v4 — Loads .ttf files from a jsdelivr CDN as **URL strings**.
// This deliberately bypasses Metro's asset resolver, which on some Expo Go
// clients hands back 0-byte responses when we require() a .ttf file (even
// one bundled inside our own /assets/fonts/). `expo-font.useFonts` supports
// URL strings natively and will download + register the font via the OS
// runtime, so this works regardless of the Metro quirk.
//
// Web is a no-op — react-native-web serves the icon fonts via CSS
// `@font-face` through Metro directly (never affected by the JS asset bug).
//
// `ICON_VECTOR_VERSION` MUST match `@expo/vector-icons` in package.json so
// the CDN glyph maps align with what the JS side expects.

import { Platform } from "react-native";
import { useFonts } from "expo-font";

const ICON_VECTOR_VERSION = "15.0.3";

const FONT_URLS = {
  // Ionicons — @expo/vector-icons registers this under lowercase `ionicons`.
  ionicons: `https://cdn.jsdelivr.net/npm/@expo/vector-icons@${ICON_VECTOR_VERSION}/build/vendor/react-native-vector-icons/Fonts/Ionicons.ttf`,
  // FontAwesome5 — family suffixes come from createIconSetFromFontAwesome5.js.
  "FontAwesome5Free-Regular": `https://cdn.jsdelivr.net/npm/@expo/vector-icons@${ICON_VECTOR_VERSION}/build/vendor/react-native-vector-icons/Fonts/FontAwesome5_Regular.ttf`,
  "FontAwesome5Free-Solid":   `https://cdn.jsdelivr.net/npm/@expo/vector-icons@${ICON_VECTOR_VERSION}/build/vendor/react-native-vector-icons/Fonts/FontAwesome5_Solid.ttf`,
  "FontAwesome5Free-Brand":   `https://cdn.jsdelivr.net/npm/@expo/vector-icons@${ICON_VECTOR_VERSION}/build/vendor/react-native-vector-icons/Fonts/FontAwesome5_Brands.ttf`,
  "FontAwesome5Free-Light":   `https://cdn.jsdelivr.net/npm/@expo/vector-icons@${ICON_VECTOR_VERSION}/build/vendor/react-native-vector-icons/Fonts/FontAwesome5_Regular.ttf`,
};

export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts(Platform.OS === "web" ? {} : FONT_URLS);
