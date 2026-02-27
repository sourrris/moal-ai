import * as DialogPrimitive from '@radix-ui/react-dialog';

import { cn } from '../lib/cn';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="ui-dialog-overlay" />
      <DialogPrimitive.Content className={cn('ui-dialog-content', className)}>{children}</DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogTitle({ children }: { children: React.ReactNode }) {
  return <DialogPrimitive.Title className="ui-dialog-title">{children}</DialogPrimitive.Title>;
}

export function DialogDescription({ children }: { children: React.ReactNode }) {
  return <DialogPrimitive.Description className="ui-dialog-description">{children}</DialogPrimitive.Description>;
}
