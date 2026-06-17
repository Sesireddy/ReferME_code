// Tiny imperative success-dialog API.
// Use anywhere: import { successAlert } from "@/src/lib/successAlert";
//   successAlert.show({ title: "...", message: "...", onOk: () => router.back() });
//   successAlert.show({ title: "...", message: "...", intent: "warning" });

export type AlertIntent = "success" | "warning" | "info" | "error";

export type SuccessAlertCfg = {
  title: string;
  message?: string;
  okLabel?: string;
  intent?: AlertIntent;
  onOk?: () => void;
};

type Listener = (cfg: SuccessAlertCfg | null) => void;

let listeners: Listener[] = [];

export const successAlert = {
  show(cfg: SuccessAlertCfg) {
    listeners.forEach((l) => l(cfg));
  },
  close() {
    listeners.forEach((l) => l(null));
  },
  subscribe(fn: Listener): () => void {
    listeners.push(fn);
    return () => {
      listeners = listeners.filter((l) => l !== fn);
    };
  },
};
