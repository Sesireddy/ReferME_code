// Icon font loader for Expo apps.
//
// Iter 70 v2 — Uses `@expo/vector-icons` bundled font shortcuts (`.font`)
// via `expo-font`'s `useFonts`. Each font family's `.font` value is a
// mapping like `{ Ionicons: require("Ionicons.ttf") }` that points at the
// .ttf files bundled inside the @expo/vector-icons npm package, so Metro
// resolves them locally — no CDN, no network dependency.
//
// Web is intentionally a no-op — `react-native-web` already serves the
// icon font via CSS `@font-face` through Metro so JS-level font loading
// on web actually breaks it (Metro can return 0-byte responses for the
// bundled .ttf).
//
// Only the families the app actually uses are loaded to keep startup lean.

import { Platform } from "react-native";
import { useFonts } from "expo-font";
import { Ionicons, FontAwesome5 } from "@expo/vector-icons";

export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts(
    Platform.OS === "web"
      ? {}
      : {
          ...Ionicons.font,
          ...FontAwesome5.font,
        },
  );
