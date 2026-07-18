// Icon font loader for Expo apps.
//
// Iter 70 — Load @expo/vector-icons .ttf files from a jsdelivr CDN on ALL
// native platforms (iOS + Android, incl. Expo Go). Web is intentionally a
// no-op because react-native-web serves the bundled font via CSS `@font-face`
// through Metro without any JS font loading (that path always works). This
// avoids the Metro asset-resolver bug where local `require`d .ttf files come
// back with 0 bytes under Expo Go / native dev servers.
//
// ICON_VECTOR_VERSION must match `@expo/vector-icons` in package.json.

import { Platform } from "react-native";
import { useFonts } from "expo-font";

const ICON_VECTOR_VERSION = "15.0.3";

// Only the icon families actually referenced by the app (verified via
// grep across `/app/*`). Adding a family here loads it at boot.
const ICON_FAMILIES = ["Ionicons", "FontAwesome5_Solid", "FontAwesome5_Brands", "FontAwesome5_Regular"] as const;
type IconFamily = (typeof ICON_FAMILIES)[number];

const iconFontMap = (): Record<IconFamily, string> =>
  Object.fromEntries(
    ICON_FAMILIES.map((f) => [
      f,
      `https://cdn.jsdelivr.net/npm/@expo/vector-icons@${ICON_VECTOR_VERSION}/build/vendor/react-native-vector-icons/Fonts/${f}.ttf`,
    ]),
  ) as Record<IconFamily, string>;

export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts(Platform.OS === "web" ? {} : iconFontMap());
