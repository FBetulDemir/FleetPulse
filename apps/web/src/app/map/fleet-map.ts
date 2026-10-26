import {
  Component,
  DestroyRef,
  ElementRef,
  ViewEncapsulation,
  afterNextRender,
  afterRenderEffect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import * as L from 'leaflet';

import { ColorScheme } from '../charts/color-scheme';
import { VesselRow } from '../fleet/vessel-row';
import {
  PositionedVessel,
  markerIcon,
  markerKey,
  markerLabelElement,
  markerPopup,
  positioned,
} from './fleet-map-markers';

/**
 * OpenStreetMap's standard tiles. Their usage policy allows light use like this demo,
 * with visible attribution and a Referer header. There is no dark style; dark mode
 * darkens the tiles with a CSS filter instead (see fleet-map.scss).
 */
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const GOTHENBURG: L.LatLngTuple = [57.67, 11.8];

interface VesselMarker {
  marker: L.Marker;
  /** See markerKey: the icon and label are only replaced when this changes. */
  key: string;
  /** The latest data, read by the popup whenever it opens or refreshes. */
  vessel: PositionedVessel;
}

@Component({
  selector: 'app-fleet-map',
  imports: [MatButtonModule, MatIconModule],
  templateUrl: './fleet-map.html',
  styleUrl: './fleet-map.scss',
  // Leaflet creates its own DOM, so its styles and the marker styles must be global.
  encapsulation: ViewEncapsulation.None,
  host: { '[class.fp-map-dark]': "scheme() === 'dark'" },
})
export class FleetMap {
  readonly vessels = input.required<readonly VesselRow[]>();

  private readonly container = viewChild.required<ElementRef<HTMLElement>>('map');
  protected readonly scheme = inject(ColorScheme).scheme;
  private readonly router = inject(Router);

  private map?: L.Map;
  private readonly markers = new Map<string, VesselMarker>();
  /** Vessels shown by the last automatic zoom; null once the user has moved the map. */
  private autoFittedCount: number | null = 0;

  constructor() {
    afterNextRender(() => {
      this.map = L.map(this.container().nativeElement, {
        center: GOTHENBURG,
        zoom: 11,
        // The mouse wheel scrolls the page, not the map; zoom with the buttons,
        // double-click or pinch instead.
        scrollWheelZoom: false,
      });
      L.tileLayer(TILE_URL, {
        attribution: ATTRIBUTION,
        maxZoom: 19,
        referrerPolicy: 'strict-origin-when-cross-origin',
      }).addTo(this.map);
      // Once the user pans, stop zooming automatically so their view is kept.
      this.map.on('dragstart', () => (this.autoFittedCount = null));
    });

    afterRenderEffect(() => {
      const vessels = positioned(this.vessels());
      if (!this.map) return;
      this.syncMarkers(vessels);
      // Vessels report one by one at first: zoom again whenever more appear.
      if (this.autoFittedCount !== null && vessels.length > this.autoFittedCount) {
        this.fitToFleet();
        this.autoFittedCount = vessels.length;
      }
    });

    inject(DestroyRef).onDestroy(() => this.map?.remove());
  }

  /** Zooms to show every vessel. */
  fitToFleet(): void {
    const points = positioned(this.vessels()).map(
      (v) => [v.latitude, v.longitude] satisfies L.LatLngTuple,
    );
    if (this.map && points.length > 0) {
      this.map.fitBounds(L.latLngBounds(points), { padding: [48, 48], maxZoom: 13 });
    }
  }

  private syncMarkers(vessels: PositionedVessel[]): void {
    const seen = new Set<string>();
    for (const vessel of vessels) {
      seen.add(vessel.vesselId);
      const existing = this.markers.get(vessel.vesselId);
      if (existing) {
        this.updateMarker(existing, vessel);
      } else {
        this.markers.set(vessel.vesselId, this.createMarker(vessel));
      }
    }
    for (const [id, { marker }] of this.markers) {
      if (!seen.has(id)) {
        marker.remove();
        this.markers.delete(id);
      }
    }
  }

  private createMarker(vessel: PositionedVessel): VesselMarker {
    // The popup function below reads entry.vessel, so the entry exists before the marker.
    const entry = { key: markerKey(vessel), vessel } as VesselMarker;
    entry.marker = L.marker([vessel.latitude, vessel.longitude], {
      icon: this.icon(vessel),
      title: vessel.name,
      alt: vessel.name,
      keyboard: true,
    })
      .bindTooltip(markerLabelElement(vessel), {
        permanent: true,
        direction: 'right',
        offset: [12, 0],
        className: 'fp-marker-label',
      })
      // A function, so the popup shows the latest data each time it opens.
      .bindPopup(() =>
        markerPopup(entry.vessel, (id) => void this.router.navigate(['/vessels', id])),
      )
      .addTo(this.map!);
    return entry;
  }

  /**
   * Updates a marker in place. Replacing it would close an open popup every time the
   * vessel turned or changed state.
   */
  private updateMarker(entry: VesselMarker, vessel: PositionedVessel): void {
    entry.vessel = vessel;
    entry.marker.setLatLng([vessel.latitude, vessel.longitude]);
    const key = markerKey(vessel);
    if (key !== entry.key) {
      entry.key = key;
      entry.marker.setIcon(this.icon(vessel));
      entry.marker.setTooltipContent(markerLabelElement(vessel));
    }
    if (entry.marker.isPopupOpen()) entry.marker.getPopup()?.update();
  }

  private icon(vessel: PositionedVessel): L.DivIcon {
    return L.divIcon({ html: markerIcon(vessel), className: '', iconSize: [24, 24] });
  }
}
