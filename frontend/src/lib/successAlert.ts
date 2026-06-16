// Tiny imperative success-dialog API.
// Use anywhere: import { successAlert } from "@/src/lib/successAlert";
//   successAlert.show({ title: "Application Submitted", message: "Your job application has been submitted successfully.", onOk: () => router.back() });

export type SuccessAlertCfg = {
  title: string;
  message?: string;
  okLabel?: string;
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
