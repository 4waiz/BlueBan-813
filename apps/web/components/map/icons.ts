/** Map glyphs rendered from inline SVG into MapLibre images (no sprite server). */
const svg = (path: string, color: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
    <circle cx="20" cy="20" r="17" fill="#071024" fill-opacity="0.92" stroke="${color}" stroke-width="2"/>
    <g transform="translate(8 8)" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</g>
  </svg>`;

export const MAP_ICONS: Record<string, string> = {
  DESALINATION_PLANT: svg('<path d="M12 2.5c3 4 5 6.6 5 9.2a5 5 0 0 1-10 0c0-2.6 2-5.2 5-9.2z"/><path d="M4 21h16M6 21v-4M18 21v-4"/>', "#27C3F3"),
  POWER_PLANT: svg('<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>', "#FFC23D"),
  PORT: svg('<circle cx="12" cy="5" r="2.5"/><path d="M12 7.5V22M5 13a7 7 0 0 0 14 0M8 11H4M20 11h-4"/>', "#93A6CB"),
  OIL_TERMINAL: svg('<path d="M4 20h16M6 20V9l6-5 6 5v11M10 20v-6h4v6"/>', "#FF8A3D"),
  PUBLIC_BEACH: svg('<path d="M4 20c3-2 5-2 8 0s5 2 8 0M12 4v10M6 9a6 6 0 0 1 12 0z"/>', "#23D484"),
  STATION: svg('<path d="M12 3v18M5 8l7-5 7 5M7 21h10"/><circle cx="12" cy="12" r="2"/>', "#8B7BFF"),
  BUOY: svg('<path d="M12 3v4M8 7h8l-1 9H9zM5 19c2-1.5 4-1.5 7 0s5 1.5 7 0"/>', "#8B7BFF"),
  CUSTOM: svg('<circle cx="12" cy="12" r="5"/>', "#EAF1FF"),
  INDUSTRIAL_INTAKE: svg('<path d="M4 20V10l5 3V10l5 3V6h6v14z"/>', "#FFC23D"),
};

export async function registerIcons(map: import("maplibre-gl").Map) {
  await Promise.all(Object.entries(MAP_ICONS).map(([name, markup]) => new Promise<void>((resolve) => {
    if (map.hasImage(`ic-${name}`)) return resolve();
    const img = new Image(40, 40);
    img.onload = () => { if (!map.hasImage(`ic-${name}`)) map.addImage(`ic-${name}`, img, { pixelRatio: 2 }); resolve(); };
    img.onerror = () => resolve();
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
  })));
}
