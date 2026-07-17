import { useEffect } from "react";
import { Alert, Platform, BackHandler } from "react-native";
import { useNavigation } from "@react-navigation/native";

/**
 * Guards navigation away from a screen with unsaved changes.
 *
 * Usage:
 *   useUnsavedChangesGuard(isDirty, {
 *     title: "Unsaved Changes",
 *     message: "You have unsaved changes. Do you want to leave this page?",
 *   });
 *
 * When `isDirty` is `true`, any attempt to leave the screen (top-left back,
 * gesture back, Android hardware back) shows a confirmation dialog with
 * "Discard" (proceed with navigation) and "Continue Editing" (cancel).
 *
 * Note: The dialog is skipped when `isDirty` is `false` so pristine screens
 * do not prompt.
 */
export function useUnsavedChangesGuard(
  isDirty: boolean,
  opts?: { title?: string; message?: string; onDiscard?: () => void }
) {
  const navigation = useNavigation();

  const title = opts?.title || "Unsaved Changes";
  const message =
    opts?.message ||
    "You have unsaved changes. Do you want to leave this page?";

  // React Navigation `beforeRemove` intercepts any navigation caused by
  // header back button, gesture, or router.back().
  useEffect(() => {
    if (!isDirty) return;
    const unsub = navigation.addListener("beforeRemove", (e: any) => {
      e.preventDefault();
      Alert.alert(title, message, [
        { text: "Continue Editing", style: "cancel", onPress: () => {} },
        {
          text: "Discard",
          style: "destructive",
          onPress: () => {
            opts?.onDiscard?.();
            navigation.dispatch(e.data.action);
          },
        },
      ]);
    });
    return unsub;
  }, [navigation, isDirty, title, message, opts]);

  // Android hardware back button — covers the case where the current route
  // is the app root (no navigation to intercept) and the user presses back.
  useEffect(() => {
    if (!isDirty || Platform.OS !== "android") return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      Alert.alert(title, message, [
        { text: "Continue Editing", style: "cancel", onPress: () => {} },
        {
          text: "Discard",
          style: "destructive",
          onPress: () => {
            opts?.onDiscard?.();
            BackHandler.exitApp();
          },
        },
      ]);
      return true; // consume the event
    });
    return () => sub.remove();
  }, [isDirty, title, message, opts]);
}
