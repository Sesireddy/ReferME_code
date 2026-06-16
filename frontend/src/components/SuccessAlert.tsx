import React, { useEffect, useState } from "react";
import { Modal, View, StyleSheet, TouchableOpacity, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Txt } from "./Txt";
import { colors, radius } from "@/src/theme/tokens";
import { successAlert, SuccessAlertCfg } from "@/src/lib/successAlert";

/**
 * SuccessAlertHost — mount ONCE at the app root (in app/_layout.tsx).
 * Renders a consistent, beautiful success modal with a SINGLE centered OK button.
 * Replaces native Alert.alert() for all success confirmations.
 */
export function SuccessAlertHost() {
  const [cfg, setCfg] = useState<SuccessAlertCfg | null>(null);

  useEffect(() => successAlert.subscribe(setCfg), []);

  const onPressOk = () => {
    const cb = cfg?.onOk;
    successAlert.close();
    // Defer to next tick so the modal closes before navigation runs
    if (cb) setTimeout(cb, 0);
  };

  if (!cfg) return null;

  return (
    <Modal visible transparent animationType="fade" onRequestClose={successAlert.close} statusBarTranslucent>
      <Pressable style={styles.backdrop} onPress={() => { /* tap outside does nothing */ }}>
        <View style={styles.card}>
          <View style={styles.iconWrap}>
            <Ionicons name="checkmark-circle" size={56} color={colors.success} />
          </View>
          <Txt variant="h2" style={styles.title}>
            {cfg.title}
          </Txt>
          {cfg.message ? (
            <Txt style={styles.message}>{cfg.message}</Txt>
          ) : null}
          <TouchableOpacity
            testID="success-ok-btn"
            onPress={onPressOk}
            activeOpacity={0.85}
            style={styles.okBtn}
            accessibilityRole="button"
            accessibilityLabel="OK"
          >
            <Txt style={styles.okLabel}>{cfg.okLabel || "OK"}</Txt>
          </TouchableOpacity>
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
  },
  card: {
    width: "100%",
    maxWidth: 360,
    backgroundColor: colors.surface,
    borderRadius: radius.xxl,
    paddingHorizontal: 22,
    paddingTop: 22,
    paddingBottom: 18,
    alignItems: "center",
    // shadow
    shadowColor: "#000",
    shadowOpacity: 0.18,
    shadowOffset: { width: 0, height: 10 },
    shadowRadius: 20,
    elevation: 12,
  },
  iconWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: (colors.success || "#10B981") + "1F",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  title: {
    textAlign: "center",
    marginTop: 4,
  },
  message: {
    textAlign: "center",
    color: colors.textSecondary,
    marginTop: 8,
    lineHeight: 20,
  },
  okBtn: {
    marginTop: 18,
    minWidth: 140,
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  okLabel: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
});
