import { useEffect, useRef, type ReactNode } from "react";
import styles from "./Sheet.module.css";

export interface SheetProps {
  title: string;
  /** Refused while something irreversible is in flight: the backdrop and Escape are both one
   *  accidental tap away, and a half-sent delete has no undo to offer. */
  busy?: boolean;
  onClose: () => void;
  children: ReactNode;
  /** The row of buttons at the bottom, where a thumb reaches. */
  actions: ReactNode;
}

/** A dialog that comes up from the bottom edge. `<dialog>` is not used: its `showModal` gives the
 *  backdrop and the focus trap, but Safari on iOS still scrolls the page behind it, which on a phone
 *  is the whole screen moving under a form. */
export function Sheet({ title, busy = false, onClose, children, actions }: SheetProps) {
  const sheet = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  useEffect(() => {
    // The first field, or the sheet itself — so a screen reader lands inside the dialog rather than
    // staying on the button that opened it, which is now behind a backdrop.
    const first = sheet.current?.querySelector<HTMLElement>("input, select, textarea, button");
    (first ?? sheet.current)?.focus();
  }, []);

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div
        ref={sheet}
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div className={styles.grip} aria-hidden />
        <h2 className={styles.title}>{title}</h2>
        <div className={styles.body}>{children}</div>
        <div className={styles.actions}>{actions}</div>
      </div>
    </div>
  );
}
