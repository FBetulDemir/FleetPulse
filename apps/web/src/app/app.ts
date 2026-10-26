import { Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterOutlet } from '@angular/router';

import { AuthService } from './auth/auth.service';
import { LiveConnection } from './live/live-connection';

const SOCKET_LABELS = {
  connecting: 'Connecting…',
  open: 'Connected',
  reconnecting: 'Reconnecting…',
} as const;

@Component({
  selector: 'app-root',
  imports: [MatButtonModule, MatIconModule, MatToolbarModule, RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly connection = inject(LiveConnection);

  protected readonly user = this.auth.user;
  protected readonly socketState = this.connection.state;
  protected readonly socketLabel = computed(() => SOCKET_LABELS[this.socketState()]);

  protected signOut(): Promise<void> {
    return this.auth.logout();
  }
}
