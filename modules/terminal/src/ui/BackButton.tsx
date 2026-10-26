import { Button, type ButtonSize } from "./Button";

/**
 * The way back to the list or menu a pane was opened from, written "← {where}". It names the destination rather than
 * saying "Back", because a view reached from two places (a team's runs from the editor and from the catalogue) must say
 * which one it returns to.
 */
export function BackButton({
  label,
  onClick,
  size,
}: {
  label: string;
  onClick: () => void;
  size?: ButtonSize;
}) {
  return (
    <Button size={size} onClick={onClick}>
      ← {label}
    </Button>
  );
}
