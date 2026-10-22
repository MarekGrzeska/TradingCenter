import QRCode from "qrcode";
import { useMemo } from "react";

/**
 * A start link as a code a phone can scan. Drawn here from the matrix rather than sent to an image service: the link carries
 * a one-shot secret that binds a destination, and a secret does not leave for a third party's picture. Black on white
 * whatever the theme, because a scanner reads contrast and not taste.
 */

const QUIET_ZONE = 4;

export function QrCode({ text, label }: { text: string; label: string }) {
  const cells = useMemo(() => {
    const { modules } = QRCode.create(text, { errorCorrectionLevel: "M" });
    const size = modules.size;
    const dark: Array<[number, number]> = [];
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        if (modules.get(x, y)) dark.push([x, y]);
      }
    }
    return { size, dark };
  }, [text]);

  const span = cells.size + QUIET_ZONE * 2;
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${span} ${span}`}
      className="h-48 w-48 rounded bg-white"
      shapeRendering="crispEdges"
    >
      <rect width={span} height={span} fill="#ffffff" />
      {cells.dark.map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x + QUIET_ZONE} y={y + QUIET_ZONE} width={1} height={1} fill="#000000" />
      ))}
    </svg>
  );
}
