import { Alert, Platform } from "react-native";

/**
 * Cross-platform replacement for Alert.alert() that actually surfaces a message
 * on react-native-web (where RNW's built-in Alert is a no-op stub).
 *
 * - On iOS / Android  → uses the native Alert.alert with a single OK button.
 * - On web            → falls back to `window.alert(title + '\n\n' + message)`.
 *
 * Use this for any user-facing "warning"-class popups (e.g. "Not yet available")
 * that need to render on every platform.
 */
export function webSafeAlert(title: string, message?: string) {
  if (Platform.OS === "web") {
    try {
      const body = message ? `${title}\n\n${message}` : title;
      (globalThis as any)?.window?.alert?.(body);
      return;
    } catch {
      // fall through to native Alert if window.alert is unavailable
    }
  }
  Alert.alert(title, message);
}
