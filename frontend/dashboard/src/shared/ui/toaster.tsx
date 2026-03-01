import { useState, useEffect, useCallback, createContext, useContext, ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

type ToastType = 'info' | 'success' | 'warning' | 'error';

interface ToastOptions {
    id?: string;
    title: string;
    description?: string;
    type?: ToastType;
    duration?: number;
}

interface Toast extends ToastOptions {
    id: string;
    type: ToastType;
    duration: number;
}

interface ToastContextProps {
    toast: (options: ToastOptions) => void;
    dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextProps | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const toast = useCallback((options: ToastOptions) => {
        const id = options.id || Math.random().toString(36).substring(2, 9);

        setToasts((prev) => {
            // Prevent duplicates with same ID
            if (prev.some(t => t.id === id)) return prev;

            return [...prev, {
                ...options,
                id,
                type: options.type || 'info',
                duration: options.duration || 5000,
            }];
        });

        // Auto dismiss
        if (options.duration !== Infinity) {
            setTimeout(() => {
                dismiss(id);
            }, options.duration || 5000);
        }
    }, []);

    const dismiss = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    return (
        <ToastContext.Provider value={{ toast, dismiss }}>
            {children}
            {typeof document !== 'undefined' && createPortal(
                <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none w-full max-w-sm">
                    {toasts.map((t) => (
                        <div
                            key={t.id}
                            className={`p-4 rounded-lg shadow-lg border pointer-events-auto flex justify-between items-start animate-in slide-in-from-right-full fade-in duration-300
                ${t.type === 'info' ? 'bg-[var(--surface-color)] border-[var(--border-color)] text-[var(--text-primary)]' : ''}
                ${t.type === 'success' ? 'bg-green-950 border-green-800 text-green-100' : ''}
                ${t.type === 'warning' ? 'bg-yellow-950 border-yellow-800 text-yellow-100' : ''}
                ${t.type === 'error' ? 'bg-red-950 border-red-800 text-red-100' : ''}
              `}
                        >
                            <div className="flex flex-col gap-1 pr-4">
                                <h4 className="font-semibold text-sm">{t.title}</h4>
                                {t.description && <p className="text-sm opacity-90">{t.description}</p>}
                            </div>
                            <button
                                onClick={() => dismiss(t.id)}
                                className="opacity-50 hover:opacity-100 transition-opacity p-1 -mr-2 -mt-2"
                                aria-label="Close"
                            >
                                <X size={16} />
                            </button>
                        </div>
                    ))}
                </div>,
                document.body
            )}
        </ToastContext.Provider>
    );
}

export function useToast() {
    const context = useContext(ToastContext);
    if (context === undefined) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
}
