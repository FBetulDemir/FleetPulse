import { FRESHNESS_LABELS, VesselRow } from '../fleet/vessel-row';

export interface PositionedVessel extends VesselRow {
  latitude: number;
  longitude: number;
}

export function positioned(rows: readonly VesselRow[]): PositionedVessel[] {
  return rows.filter(
    (row): row is PositionedVessel => row.latitude !== null && row.longitude !== null,
  );
}

/** Moving vessels point in their direction of travel; others are drawn as a dot. */
export function markerShape(vessel: VesselRow): 'arrow' | 'dot' {
  return vessel.freshness === 'live' && vessel.status === 'underway' ? 'arrow' : 'dot';
}

/**
 * Everything that changes how a marker looks. The marker is only rebuilt when this
 * changes, not on every position update (which would also steal keyboard focus).
 * Course is rounded to 5 degrees for the same reason.
 */
export function markerKey(vessel: VesselRow): string {
  const course = Math.round((vessel.courseDegrees ?? 0) / 5) * 5;
  return [vessel.name, vessel.freshness, markerShape(vessel), course].join('|');
}

/** The map label: the name, plus the state when it is not live (not color alone). */
export function markerLabel(vessel: VesselRow): string {
  return vessel.freshness === 'live'
    ? vessel.name
    : `${vessel.name} · ${FRESHNESS_LABELS[vessel.freshness].label}`;
}

/**
 * Builds marker content with DOM APIs and textContent only. Vessel names are user
 * data, and Leaflet inserts string content as HTML.
 */
export function markerIcon(vessel: VesselRow): HTMLElement {
  const icon = document.createElement('span');
  icon.className = `fp-marker fp-marker--${vessel.freshness} fp-marker--${markerShape(vessel)}`;
  if (markerShape(vessel) === 'arrow') {
    icon.style.transform = `rotate(${Math.round(vessel.courseDegrees ?? 0)}deg)`;
  }
  return icon;
}

export function markerLabelElement(vessel: VesselRow): HTMLElement {
  const label = document.createElement('span');
  label.textContent = markerLabel(vessel);
  return label;
}

export function markerPopup(vessel: VesselRow, openDetails: (id: string) => void): HTMLElement {
  const popup = document.createElement('div');
  popup.className = 'fp-popup';

  const title = document.createElement('strong');
  title.textContent = vessel.name;
  popup.append(title);

  const facts = [
    FRESHNESS_LABELS[vessel.freshness].label,
    vessel.speedKnots === null ? null : `${vessel.speedKnots.toFixed(1)} kn`,
    vessel.batteryPercent === null ? null : `Battery ${Math.round(vessel.batteryPercent)} %`,
  ].filter((fact): fact is string => fact !== null);
  const details = document.createElement('span');
  details.textContent = facts.join(' · ');
  popup.append(details);

  const id = vessel.id;
  if (id) {
    const link = document.createElement('a');
    link.href = `/vessels/${id}`;
    link.textContent = 'Open details';
    // Navigate inside the app instead of reloading the page.
    link.addEventListener('click', (event) => {
      event.preventDefault();
      openDetails(id);
    });
    popup.append(link);
  }
  return popup;
}
