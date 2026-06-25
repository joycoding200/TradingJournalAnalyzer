import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react";

interface Toast {
  id: number;
  type: "success" | "error" | "warning" | "info";
  message: string;
  exiting?: boolean;
}

interface ToastContextType {
  toasts: Toast[];
  addToast: (type: Toast["type"], message: string) => void;
  removeToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextType>({
  toasts: [],
  addToast: () => {},
  removeToast: () => {},
});

// Module-scoped counter so ids stay unique across HMR remounts
let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  // Track pending timers so we can cancel them on manual dismiss.
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const removeToast = useCallback((id: number) => {
    // Cancel any pending auto-dismiss for this toast.
    const t = timers.current.get(id);
    if (t) {
      clearTimeout(t);
      timers.current.delete(id);
    }
    // Mark exiting first → plays the out-animation, then drop from DOM.
    setToasts((prev) => prev.map((x) => (x.id === id ? { ...x, exiting: true } : x)));
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 200);
  }, []);

  const addToast = useCallback(
    (type: Toast["type"], message: string) => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, type, message }]);
      const timer = setTimeout(() => removeToast(id), 4000);
      timers.current.set(id, timer);
    },
    [removeToast]
  );

  const borderColor: Record<Toast["type"], string> = {
    success: "border-success",
    error: "border-danger",
    warning: "border-warning",
    info: "border-accent",
  };
  const iconColor: Record<Toast["type"], string> = {
    success: "text-success",
    error: "text-danger",
    warning: "text-warning",
    info: "text-accent",
  };
  const icons: Record<Toast["type"], string> = {
    success: "✓",
    error: "✗",
    warning: "⚠",
    info: "ℹ",
  };

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      {/* Toast container */}
      <div
        className="fixed right-4 top-4 z-[100] flex max-w-[360px] flex-col gap-2"
        role="region"
        aria-label="通知"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="alert"
            className={[
              "flex cursor-pointer items-start gap-2 rounded-[10px] border bg-bg-secondary p-3 text-[14px] text-text-primary shadow-[0_4px_12px_rgba(0,0,0,0.3)]",
              borderColor[toast.type],
              toast.exiting ? "animate-toast-out" : "animate-toast-in",
            ].join(" ")}
            onClick={() => removeToast(toast.id)}
          >
            <span className={`text-[15px] font-bold ${iconColor[toast.type]}`}>
              {icons[toast.type]}
            </span>
            <span className="flex-1">{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
