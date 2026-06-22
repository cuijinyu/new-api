import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";

export type ToastTone = "success" | "error" | "loading" | "info";

export type Toast = {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
};

type ToastContextValue = {
  push: (toast: Omit<Toast, "id"> & { id?: string }) => string;
  update: (id: string, patch: Partial<Omit<Toast, "id">>) => void;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

let toastSeq = 0;
function nextId() {
  toastSeq += 1;
  return `toast-${Date.now()}-${toastSeq}`;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const scheduleAutoDismiss = useCallback(
    (toast: Toast) => {
      const existing = timers.current.get(toast.id);
      if (existing) clearTimeout(existing);
      // loading 态不自动消失，等待 update 后再计时。
      if (toast.tone === "loading") return;
      const ttl = toast.tone === "error" ? 6000 : 3600;
      const timer = setTimeout(() => dismiss(toast.id), ttl);
      timers.current.set(toast.id, timer);
    },
    [dismiss],
  );

  const push = useCallback(
    (toast: Omit<Toast, "id"> & { id?: string }) => {
      const id = toast.id || nextId();
      const next: Toast = { id, tone: toast.tone, title: toast.title, description: toast.description };
      setToasts((prev) => [...prev.filter((item) => item.id !== id), next]);
      scheduleAutoDismiss(next);
      return id;
    },
    [scheduleAutoDismiss],
  );

  const update = useCallback(
    (id: string, patch: Partial<Omit<Toast, "id">>) => {
      setToasts((prev) => {
        const found = prev.find((item) => item.id === id);
        if (!found) return prev;
        const merged: Toast = { ...found, ...patch };
        scheduleAutoDismiss(merged);
        return prev.map((item) => (item.id === id ? merged : item));
      });
    },
    [scheduleAutoDismiss],
  );

  const value = useMemo(() => ({ push, update, dismiss }), [push, update, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const toneIcon: Record<ToastTone, ReactNode> = {
  success: <CheckCircle2 size={18} />,
  error: <XCircle size={18} />,
  loading: <Loader2 size={18} className="spin" />,
  info: <Info size={18} />,
};

function ToastViewport({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: string) => void }) {
  if (!toasts.length) return null;
  return (
    <div className="toast-viewport" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tone}`}>
          <span className="toast-icon">{toneIcon[toast.tone]}</span>
          <div className="toast-body">
            <strong>{toast.title}</strong>
            {toast.description ? <span>{toast.description}</span> : null}
          </div>
          <button type="button" className="toast-close" onClick={() => onDismiss(toast.id)} aria-label="关闭">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast 必须在 ToastProvider 内使用");
  }
  return ctx;
}
