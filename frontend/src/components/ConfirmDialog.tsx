import React from "react";
import { Modal, View, StyleSheet } from "react-native";
import { Txt } from "@/src/components/Txt";
import { Button } from "@/src/components/Button";
import { colors, radius } from "@/src/theme/tokens";

/**
 * Cross-platform confirm dialog. Uses a Modal so it works identically on
 * iOS, Android, and react-native-web (which silently drops 3-button Alert.alert).
 */
export function ConfirmDialog({
  visible,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  onCancel,
}: {
  visible: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.bg}>
        <View style={styles.box}>
          <Txt variant="h2" style={{ textAlign: "center" }}>{title}</Txt>
          {message ? (
            <Txt variant="muted" style={{ textAlign: "center", marginTop: 8 }}>{message}</Txt>
          ) : null}
          <View style={{ flexDirection: "row", gap: 10, marginTop: 22, justifyContent: cancelLabel ? "flex-start" : "center" }}>
            {cancelLabel ? (
              <Button
                testID="confirm-cancel"
                title={cancelLabel}
                variant="secondary"
                onPress={onCancel}
                style={{ flex: 1 }}
              />
            ) : null}
            <Button
              testID="confirm-ok"
              title={confirmLabel}
              onPress={onConfirm}
              style={cancelLabel ? { flex: 1, ...(destructive ? { backgroundColor: colors.error } : {}) } : { minWidth: 160, paddingHorizontal: 32, ...(destructive ? { backgroundColor: colors.error } : {}) }}
            />
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center", justifyContent: "center", padding: 24 },
  box: { backgroundColor: colors.bg, borderRadius: radius.xxl, padding: 22, width: "100%", maxWidth: 380 },
});
