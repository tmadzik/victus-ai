'use client';

import type { BleSupportInfo, HrMeasurement } from './types';

/**
 * Web Bluetooth Heart Rate Service wrapper.
 *
 * - GATT service UUID: 0x180D
 * - Heart Rate Measurement characteristic: 0x2A37 (notifications)
 *
 * Spec reference (Bluetooth SIG GATT.HRS.4.0):
 *   Byte 0    Flags
 *               bit 0  HR value format (0 = uint8, 1 = uint16)
 *               bit 1-2 Sensor contact status
 *               bit 3  Energy Expended present
 *               bit 4  RR-Interval present
 *   Byte 1..  HR value (uint8 or uint16 LE)
 *   ...       Energy Expended (uint16 LE) if bit 3
 *   ...       RR intervals (uint16 LE, units of 1/1024 s) if bit 4
 *
 * The parser tolerates short payloads (some devices omit trailing RR
 * intervals on quiet beats) and never throws on a malformed frame —
 * a returned ``null`` lets the recorder simply skip the sample.
 */

export const HEART_RATE_SERVICE = 'heart_rate' as const; // 0x180D
export const HEART_RATE_MEASUREMENT = 'heart_rate_measurement' as const; // 0x2A37

export function detectBleSupport(): BleSupportInfo {
  if (typeof navigator === 'undefined' || !('bluetooth' in navigator)) {
    return {
      apiAvailable: false,
      adapterAvailable: null,
      reason:
        'navigator.bluetooth is unavailable. Use Chrome or Edge — Safari and Firefox do not implement Web Bluetooth.',
    };
  }
  return { apiAvailable: true, adapterAvailable: null, reason: null };
}

export async function probeAdapter(): Promise<BleSupportInfo> {
  const base = detectBleSupport();
  if (!base.apiAvailable) return base;
  try {
    const bt = navigator.bluetooth as {
      getAvailability?: () => Promise<boolean>;
    };
    const available = bt.getAvailability ? await bt.getAvailability() : true;
    return {
      apiAvailable: true,
      adapterAvailable: available,
      reason: available ? null : 'Bluetooth adapter is off or unavailable.',
    };
  } catch (err) {
    return {
      apiAvailable: true,
      adapterAvailable: null,
      reason: err instanceof Error ? err.message : String(err),
    };
  }
}

export interface BleHrConnection {
  device: BluetoothDevice;
  server: BluetoothRemoteGATTServer;
  characteristic: BluetoothRemoteGATTCharacteristic;
  disconnect: () => void;
}

export async function requestHrDevice(): Promise<BluetoothDevice> {
  return navigator.bluetooth.requestDevice({
    filters: [{ services: [HEART_RATE_SERVICE] }],
    optionalServices: ['battery_service', 'device_information'],
  });
}

export async function connectHrService(
  device: BluetoothDevice,
): Promise<BleHrConnection> {
  if (!device.gatt) {
    throw new Error('Selected device does not expose a GATT server.');
  }
  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(HEART_RATE_SERVICE);
  const characteristic = await service.getCharacteristic(HEART_RATE_MEASUREMENT);
  await characteristic.startNotifications();

  const disconnect = (): void => {
    characteristic.stopNotifications().catch(() => undefined);
    try {
      device.gatt?.disconnect();
    } catch {
      // ignore — disconnects are best-effort cleanup
    }
  };

  return { device, server, characteristic, disconnect };
}

export function parseHeartRateMeasurement(
  view: DataView,
  capture_start_ms: number,
): HrMeasurement | null {
  if (view.byteLength < 2) return null;
  const flags = view.getUint8(0);
  const hrUint16 = (flags & 0x01) !== 0;
  const contactSupported = (flags & 0x04) !== 0;
  const contactDetected = (flags & 0x02) !== 0;
  const energyPresent = (flags & 0x08) !== 0;
  const rrPresent = (flags & 0x10) !== 0;

  let offset = 1;
  let hr_bpm: number;
  if (hrUint16) {
    if (view.byteLength < offset + 2) return null;
    hr_bpm = view.getUint16(offset, true);
    offset += 2;
  } else {
    hr_bpm = view.getUint8(offset);
    offset += 1;
  }
  if (hr_bpm < 30 || hr_bpm > 240) return null;

  if (energyPresent) offset += 2;

  const rr_intervals_ms: number[] = [];
  if (rrPresent) {
    while (offset + 1 < view.byteLength) {
      const rr_1024 = view.getUint16(offset, true);
      rr_intervals_ms.push((rr_1024 / 1024) * 1000);
      offset += 2;
    }
  }

  const contact = contactSupported
    ? contactDetected
      ? 'detected'
      : 'not_detected'
    : 'no_support';

  return {
    t_ms: Math.max(0, performance.now() - capture_start_ms),
    hr_bpm,
    rr_intervals_ms,
    contact,
  };
}
