// Icon font loader for Expo apps.
//
// Iter 70 v3 — Bundles the @expo/vector-icons .ttf files INSIDE this app's
// own `assets/fonts/` folder and loads them via `require()`.
//
// Why: On several Expo Go devices, `require`ing from `node_modules/@expo/vector-icons/...`
// returns 0-byte payloads from the Metro asset resolver (long-standing bug).
// Copying the .ttf files under our own `assets/` folder side-steps that
// entirely — Metro treats them like any other app asset.
//
// Web is intentionally a no-op — react-native-web serves the bundled font
// via CSS `@font-face` through Metro directly, so no JS-level loading needed.
//
// The font-family names below MUST match what `@expo/vector-icons` uses
// internally, otherwise `<Ionicons>` / `<FontAwesome5>` glyphs render as
// empty boxes. Verified against the library source in
// `node_modules/@expo/vector-icons/build/`:
//   * Ionicons.js               → 'ionicons'
//   * createIconSetFromFontAwesome5.js → `FontAwesome5Free-Regular`, `-Solid`,
//                                       `-Brand`, `-Light` (Light aliases Regular)

import { Platform } from "react-native";
import { useFonts } from "expo-font";

const nativeIconFontMap = () => ({
  ionicons: require("../../assets/fonts/Ionicons.ttf"),
  "FontAwesome5Free-Regular": require("../../assets/fonts/FontAwesome5_Regular.ttf"),
  "FontAwesome5Free-Solid": require("../../assets/fonts/FontAwesome5_Solid.ttf"),
  "FontAwesome5Free-Brand": require("../../assets/fonts/FontAwesome5_Brands.ttf"),
  "FontAwesome5Free-Light": require("../../assets/fonts/FontAwesome5_Regular.ttf"),
});

export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts(Platform.OS === "web" ? {} : nativeIconFontMap());
