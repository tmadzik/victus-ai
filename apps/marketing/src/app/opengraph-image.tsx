import { ImageResponse } from 'next/og';

// Static page → this image is generated once at build time and served as a
// static PNG, so the cPanel runtime never invokes the image renderer.
export const runtime = 'nodejs';

export const alt = 'Victus — Predict NCD Risk. Prevent Avoidable Claims.';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpengraphImage(): ImageResponse {
  return new ImageResponse(
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        backgroundColor: '#102117',
        padding: '72px',
        color: '#ffffff',
        fontFamily: 'sans-serif',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <div
          style={{
            display: 'flex',
            width: 44,
            height: 44,
            borderRadius: 12,
            backgroundColor: '#4aad33',
            marginRight: 18,
          }}
        />
        <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: '0.06em' }}>VICTUS</div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            display: 'flex',
            fontSize: 78,
            fontWeight: 700,
            lineHeight: 1.05,
            letterSpacing: '-0.03em',
            maxWidth: 1010,
          }}
        >
          Predict NCD Risk. Prevent Avoidable Claims.
        </div>
        <div
          style={{
            display: 'flex',
            fontSize: 30,
            color: 'rgba(255,255,255,0.7)',
            marginTop: 28,
            maxWidth: 940,
          }}
        >
          Predictive AI risk modeling and an owned physical wellness network for healthcare funders.
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            display: 'flex',
            width: '100%',
            height: 14,
            borderRadius: 9999,
            overflow: 'hidden',
          }}
        >
          <div style={{ display: 'flex', width: '71%', backgroundColor: '#37a85a' }} />
          <div style={{ display: 'flex', width: '21%', backgroundColor: '#d6a52e' }} />
          <div style={{ display: 'flex', width: '8%', backgroundColor: '#c8432f' }} />
        </div>
        <div
          style={{ display: 'flex', fontSize: 22, color: 'rgba(255,255,255,0.5)', marginTop: 18 }}
        >
          GREEN / YELLOW / RED triage · www.victusdata.com
        </div>
      </div>
    </div>,
    { ...size },
  );
}
