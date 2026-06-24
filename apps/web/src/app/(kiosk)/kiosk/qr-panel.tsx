'use client';

import QRCode from 'qrcode';
import { useEffect, useRef } from 'react';

/** Renders a QR code for the WhatsApp deep link onto a canvas (offline, no
 *  external image service — the kiosk never phones home with the nonce). */
export function QrPanel({
  value,
  size = 256,
}: {
  value: string;
  size?: number;
}): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    void QRCode.toCanvas(canvas, value, {
      width: size,
      margin: 1,
      color: { dark: '#0c1a24', light: '#ffffff' },
      errorCorrectionLevel: 'M',
    }).catch(() => {
      /* a render failure just shows a blank canvas; the deep link text is
         still displayed alongside as a fallback. */
    });
  }, [value, size]);

  return (
    <div className="rounded-3xl bg-white p-4 shadow-lg">
      <canvas ref={canvasRef} aria-label="WhatsApp verification QR code" />
    </div>
  );
}
