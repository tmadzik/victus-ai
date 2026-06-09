'use client';

import { useEffect, useState } from 'react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export function ConsentStep({
  onContinue,
}: {
  onContinue: () => void;
}): React.ReactElement {
  const [isSecure, setIsSecure] = useState(true);
  const [hasMediaDevices, setHasMediaDevices] = useState(true);
  const [permission, setPermission] =
    useState<'idle' | 'requesting' | 'granted' | 'denied'>('idle');
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  useEffect(() => {
    setIsSecure(window.isSecureContext);
    setHasMediaDevices(
      typeof navigator !== 'undefined' &&
        typeof navigator.mediaDevices !== 'undefined' &&
        typeof navigator.mediaDevices.getUserMedia === 'function',
    );
  }, []);

  const requestPermission = async (): Promise<void> => {
    setPermission('requesting');
    setErrorDetail(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 30, max: 60 },
          facingMode: 'user',
        },
        audio: false,
      });
      // Release the probe stream immediately; the capture step opens its own.
      stream.getTracks().forEach((t) => t.stop());
      setPermission('granted');
    } catch (err) {
      setPermission('denied');
      setErrorDetail(err instanceof Error ? err.message : String(err));
    }
  };

  const canContinue = isSecure && hasMediaDevices && permission === 'granted';

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set up your capture environment</CardTitle>
        <CardDescription>
          A 30-second facial video is processed entirely on the server. No
          frames are stored — only per-frame mean RGB over a forehead ROI is
          transmitted (about 10 KB total).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {!isSecure ? (
          <Alert tone="danger">
            <AlertTitle>HTTPS required</AlertTitle>
            <AlertDescription>
              The browser MediaStream API only works on{' '}
              <code className="font-mono">https://</code> or{' '}
              <code className="font-mono">localhost</code>. Open this page over
              a secure context and reload.
            </AlertDescription>
          </Alert>
        ) : null}

        {isSecure && !hasMediaDevices ? (
          <Alert tone="danger">
            <AlertTitle>Camera API unavailable</AlertTitle>
            <AlertDescription>
              <code className="font-mono">navigator.mediaDevices.getUserMedia</code>{' '}
              is not supported in this browser. Use a recent Chrome, Safari, or
              Firefox build.
            </AlertDescription>
          </Alert>
        ) : null}

        <ChecklistItem
          status={isSecure ? 'pass' : 'fail'}
          title="Secure context"
          body="HTTPS or localhost is required by the browser camera API."
        />
        <ChecklistItem
          status={hasMediaDevices ? 'pass' : 'fail'}
          title="Camera API"
          body="navigator.mediaDevices.getUserMedia must be available."
        />
        <ChecklistItem
          status={
            permission === 'granted'
              ? 'pass'
              : permission === 'denied'
                ? 'fail'
                : 'pending'
          }
          title="Camera permission"
          body={
            permission === 'granted'
              ? 'Granted — you can begin capture.'
              : permission === 'denied'
                ? errorDetail ?? 'Permission was denied. Re-enable it in browser settings.'
                : 'We will ask the browser for camera access. Microphone is never requested.'
          }
        />

        <Alert tone="info">
          <AlertTitle>Capture instructions</AlertTitle>
          <AlertDescription>
            Sit still under even, indirect lighting. Avoid backlight, fans, and
            phone notifications during the 30-second window. Look straight at
            the camera and keep your forehead unobstructed.
          </AlertDescription>
        </Alert>

        <div className="flex justify-end gap-3">
          {permission !== 'granted' ? (
            <Button
              onClick={requestPermission}
              disabled={!isSecure || !hasMediaDevices || permission === 'requesting'}
            >
              {permission === 'requesting' ? 'Requesting…' : 'Request camera access'}
            </Button>
          ) : (
            <Button onClick={onContinue} disabled={!canContinue}>
              Continue to capture
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ChecklistItem({
  status,
  title,
  body,
}: {
  status: 'pass' | 'fail' | 'pending';
  title: string;
  body: string;
}): React.ReactElement {
  const colour =
    status === 'pass'
      ? 'border-[color:var(--color-state-green-ring)]/40 bg-[color:var(--color-state-green-bg)] text-[color:var(--color-state-green-fg)]'
      : status === 'fail'
        ? 'border-[color:var(--color-state-red-ring)]/40 bg-[color:var(--color-state-red-bg)] text-[color:var(--color-state-red-fg)]'
        : 'border-brand-200 bg-brand-50 text-brand-800';
  const dot =
    status === 'pass' ? '●' : status === 'fail' ? '●' : '○';
  return (
    <div
      className={`rounded-[var(--radius-control)] border p-3 ${colour}`}
    >
      <p className="text-sm font-semibold">
        <span aria-hidden="true" className="mr-2">
          {dot}
        </span>
        {title}
      </p>
      <p className="mt-1 text-xs">{body}</p>
    </div>
  );
}
