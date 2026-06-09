'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  connectHrService,
  detectBleSupport,
  probeAdapter,
  requestHrDevice,
} from '@/lib/ble/heart-rate-service';
import { HrRecorder } from '@/lib/ble/hr-recorder';
import type { HrMeasurement } from '@/lib/ble/types';

export interface BleConnectPanelHandle {
  recorder: HrRecorder | null;
  isConnected: boolean;
}

/**
 * Connect / disconnect a BLE Heart Rate Service device and stream live HR.
 *
 * Hands a configured :class:`HrRecorder` up to the orchestrator via
 * ``onRecorderChange`` so the capture flow can ``start()`` / ``stop()`` the
 * recorder in lock-step with the rPPG capture window.
 */
export function BleConnectPanel({
  onRecorderChange,
  onDeviceLabelChange,
}: {
  onRecorderChange: (recorder: HrRecorder | null) => void;
  onDeviceLabelChange?: (label: string | null) => void;
}): React.ReactElement {
  const [support, setSupport] = useState(() => detectBleSupport());
  const [adapter, setAdapter] = useState<boolean | null>(null);
  const [device, setDevice] = useState<BluetoothDevice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [liveHr, setLiveHr] = useState<HrMeasurement | null>(null);
  const [connecting, setConnecting] = useState(false);
  const recorderRef = useRef<HrRecorder | null>(null);
  const disconnectRef = useRef<(() => void) | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let alive = true;
    void probeAdapter().then((info) => {
      if (!alive) return;
      setSupport(info);
      setAdapter(info.adapterAvailable);
    });
    return () => {
      alive = false;
    };
  }, []);

  const disconnect = useCallback((): void => {
    if (unsubscribeRef.current) unsubscribeRef.current();
    unsubscribeRef.current = null;
    if (recorderRef.current) recorderRef.current.detach();
    recorderRef.current = null;
    onRecorderChange(null);
    onDeviceLabelChange?.(null);
    if (disconnectRef.current) disconnectRef.current();
    disconnectRef.current = null;
    setDevice(null);
    setLiveHr(null);
  }, [onRecorderChange, onDeviceLabelChange]);

  useEffect(() => () => disconnect(), [disconnect]);

  const connect = useCallback(async (): Promise<void> => {
    setError(null);
    setConnecting(true);
    try {
      const dev = await requestHrDevice();
      const connection = await connectHrService(dev);

      const recorder = new HrRecorder();
      recorder.attach(connection.characteristic);
      const unsubscribe = recorder.onUpdate((sample) => setLiveHr(sample));

      recorderRef.current = recorder;
      disconnectRef.current = (): void => {
        try {
          connection.disconnect();
        } catch {
          // ignore
        }
      };
      unsubscribeRef.current = unsubscribe;

      dev.addEventListener('gattserverdisconnected', () => {
        setError('BLE device disconnected. Reconnect to continue.');
        disconnect();
      });

      setDevice(dev);
      onRecorderChange(recorder);
      onDeviceLabelChange?.(dev.name ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setConnecting(false);
    }
  }, [onRecorderChange, onDeviceLabelChange, disconnect]);

  if (!support.apiAvailable) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>BLE auto-pair</CardTitle>
          <CardDescription>
            Connect a Heart Rate Service device for hands-free reference capture.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Alert tone="warning">
            <AlertTitle>Web Bluetooth unavailable</AlertTitle>
            <AlertDescription>
              {support.reason} You can still pair manually by entering the
              reading from your reference device after the capture.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>BLE auto-pair</CardTitle>
        <CardDescription>
          Stream HR and (where supported) raw RR intervals from a chest-strap
          or pulse oximeter exposing the Heart Rate Service (0x180D). Polar
          H10, Wahoo TICKR, MyZone, and most BLE pulse oximeters work.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {adapter === false ? (
          <Alert tone="warning">
            <AlertTitle>Bluetooth adapter off</AlertTitle>
            <AlertDescription>
              Enable Bluetooth on this machine, then click Connect.
            </AlertDescription>
          </Alert>
        ) : null}

        {error ? (
          <Alert tone="danger">
            <AlertTitle>Connection error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        {device ? (
          <div className="flex items-center justify-between gap-4 rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-brand-700">
                Connected
              </p>
              <p className="mt-1 text-sm font-medium text-brand-900">
                {device.name ?? 'Unnamed Heart Rate device'}
              </p>
              <p className="text-xs text-brand-600">
                {liveHr
                  ? `Live: ${liveHr.hr_bpm.toFixed(0)} bpm` +
                    (liveHr.rr_intervals_ms.length > 0
                      ? `  ·  ${liveHr.rr_intervals_ms.length} RR intervals received this notification`
                      : '')
                  : 'Waiting for the first notification…'}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={disconnect}>
              Disconnect
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <Button onClick={connect} disabled={connecting}>
              {connecting ? 'Connecting…' : 'Connect BLE device'}
            </Button>
            <p className="text-xs text-brand-600">
              Browser opens the device picker. We only request the Heart Rate
              service; no other characteristics are read.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
