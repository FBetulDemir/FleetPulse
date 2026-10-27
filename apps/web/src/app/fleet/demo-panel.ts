import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, computed, inject, input, linkedSignal, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { firstValueFrom } from 'rxjs';

import { AuthOptions, Scenario, Vessel } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { AUTH_OPTIONS_URL } from '../auth/login-page';

export const SCENARIOS_URL = '/api/v1/demo/scenarios';

interface ScenarioButton {
  scenario: Scenario;
  label: string;
  icon: string;
  /** Shown after starting, so visitors know when to expect the alert. */
  expect: string;
}

export const SCENARIO_BUTTONS: ScenarioButton[] = [
  {
    scenario: 'overheat',
    label: 'Overheat motor',
    icon: 'thermostat',
    expect: 'A critical alert appears in about 20 seconds.',
  },
  {
    scenario: 'battery_drain',
    label: 'Drain battery',
    icon: 'battery_alert',
    expect: 'Battery alerts appear within about a minute.',
  },
  {
    scenario: 'go_offline',
    label: 'Go offline',
    icon: 'sensors_off',
    expect: 'The vessel goes offline right away.',
  },
  {
    scenario: 'invalid_data',
    label: 'Send bad data',
    icon: 'report',
    expect: 'An invalid-data alert appears right away.',
  },
];

@Component({
  selector: 'app-demo-panel',
  imports: [MatButtonModule, MatFormFieldModule, MatIconModule, MatSelectModule],
  templateUrl: './demo-panel.html',
  styleUrl: './demo-panel.scss',
})
export class DemoPanel {
  /** Registered vessels to choose from. */
  readonly vessels = input.required<readonly Vessel[]>();

  private readonly http = inject(HttpClient);
  private readonly snackBar = inject(MatSnackBar);
  private readonly auth = inject(AuthService);

  private readonly options = httpResource<AuthOptions>(() => AUTH_OPTIONS_URL);
  protected readonly enabled = computed(
    () => this.options.hasValue() && this.options.value().demo_login,
  );
  protected readonly canTrigger = computed(() => {
    const role = this.auth.user()?.role;
    return role === 'operator' || role === 'admin';
  });

  /** Defaults to the first vessel, and follows the list if it changes. */
  protected readonly vesselId = linkedSignal(() => this.vessels()[0]?.id ?? null);
  protected readonly busy = signal(false);
  protected readonly buttons = SCENARIO_BUTTONS;

  protected async trigger(scenario: Scenario): Promise<void> {
    const vessel = this.vessels().find((v) => v.id === this.vesselId());
    if (!vessel) return;
    this.busy.set(true);
    try {
      await firstValueFrom(this.http.post(SCENARIOS_URL, { vessel_id: vessel.id, scenario }));
      this.snackBar.open(startedMessage(scenario, vessel.name), 'OK', { duration: 6000 });
    } catch (error) {
      this.snackBar.open(failureMessage(error), 'Close', { duration: 6000 });
    } finally {
      this.busy.set(false);
    }
  }
}

function startedMessage(scenario: Scenario, vesselName: string): string {
  if (scenario === 'reset') return `${vesselName} is back to normal.`;
  const button = SCENARIO_BUTTONS.find((b) => b.scenario === scenario);
  return `${button?.label ?? scenario} started on ${vesselName}. ${button?.expect ?? ''}`.trim();
}

function failureMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse && error.status === 429) {
    return 'That was a lot of failures in a short time. Try again in a minute.';
  }
  return 'The scenario could not be started. Please try again.';
}
