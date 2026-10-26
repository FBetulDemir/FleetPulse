import { Component, computed, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterOutlet } from '@angular/router';

import { LiveConnection } from './live/live-connection';

const SOCKET_LABELS = {
  connecting: 'Connecting…',
  open: 'Connected',
  reconnecting: 'Reconnecting…',
} as const;

@Component({
  selector: 'app-root',
  imports: [MatIconModule, MatToolbarModule, RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly connection = inject(LiveConnection);

  protected readonly socketState = this.connection.state;
  protected readonly socketLabel = computed(() => SOCKET_LABELS[this.socketState()]);
}
