import { Platform } from "react-native";

/**
 * Read a picked file (image or PDF) as a base64 data URI, cross-platform.
 *
 * Works on:
 *  - Web:    uses `fetch(blob:URL) → blob() → FileReader.readAsDataURL()` (native browser APIs).
 *  - Native: same code path — React Native provides `fetch` + `Blob` + `FileReader` via its
 *            XHR/Blob polyfill, so this avoids the fragile `expo-file-system/legacy`
 *            `readAsStringAsync({ encoding: "base64" })` path that fails when the URI is a
 *            `blob:` URL (which is what DocumentPicker returns on web).
 *
 * If you already know the desired MIME (e.g. application/pdf) and want to normalise the
 * data-URI prefix (some browsers report octet-stream), pass `forceMime`.
 *
 * @throws if the file cannot be read or is larger than `maxBytes` (default: 5 MB).
 */
export async function fileToDataUri(uri: string, opts?: { forceMime?: string; maxBytes?: number; }): Promise<string> {
  const maxBytes = opts?.maxBytes ?? 5 * 1024 * 1024; // 5 MB payload cap (base64 ~ +33%)
  const response = await fetch(uri);
  const blob = await response.blob();
  if ((blob as any).size && (blob as any).size > maxBytes) {
    throw new Error(`File exceeds ${(maxBytes / 1024 / 1024).toFixed(0)} MB limit.`);
  }
  const dataUri: string = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("FileReader failed"));
    reader.readAsDataURL(blob);
  });
  if (opts?.forceMime && !dataUri.startsWith(`data:${opts.forceMime}`)) {
    const b64 = dataUri.split(",")[1] || "";
    return `data:${opts.forceMime};base64,${b64}`;
  }
  return dataUri;
}

/** Kept only to make the intent clear at call sites. */
export const IS_WEB = Platform.OS === "web";
