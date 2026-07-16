import { Component, forwardRef, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NG_VALUE_ACCESSOR, ControlValueAccessor } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatInputModule } from '@angular/material/input';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { CronDisplayComponent } from '../cron-display/cron-display.component';

type Frequency = 'minutes' | 'hourly' | 'daily' | 'weekly' | 'monthly';

interface DayOption {
  label: string;
  value: number;
  checked: boolean;
}

@Component({
  selector: 'app-cron-builder',
  imports: [
    CommonModule, FormsModule,
    MatFormFieldModule, MatSelectModule, MatCheckboxModule,
    MatInputModule, MatButtonToggleModule, MatSlideToggleModule,
    CronDisplayComponent,
  ],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => CronBuilderComponent),
      multi: true,
    },
  ],
  template: `
    <div class="cron-builder">
      <div class="mode-toggle">
        <mat-slide-toggle [(ngModel)]="advancedMode" (ngModelChange)="onModeChange()">
          I'll write it manually
        </mat-slide-toggle>
      </div>

      <div *ngIf="advancedMode" class="advanced-input">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Cron Expression</mat-label>
          <input matInput [(ngModel)]="rawExpression" (ngModelChange)="onRawChange($event)" placeholder="0 9 * * *">
        </mat-form-field>
        <div class="preview">
          <app-cron-display [expression]="currentExpression"></app-cron-display>
        </div>
      </div>

      <div *ngIf="!advancedMode" class="builder-controls">
        <div class="frequency-row">
          <mat-button-toggle-group [(ngModel)]="frequency" (ngModelChange)="buildExpression()">
            <mat-button-toggle value="minutes">Minutes</mat-button-toggle>
            <mat-button-toggle value="hourly">Hourly</mat-button-toggle>
            <mat-button-toggle value="daily">Daily</mat-button-toggle>
            <mat-button-toggle value="weekly">Weekly</mat-button-toggle>
            <mat-button-toggle value="monthly">Monthly</mat-button-toggle>
          </mat-button-toggle-group>
        </div>

        <div class="time-row" *ngIf="frequency === 'minutes'">
          <mat-form-field appearance="outline" class="time-field">
            <mat-label>Every</mat-label>
            <mat-select [(ngModel)]="minuteInterval" (ngModelChange)="buildExpression()">
              <mat-option *ngFor="let iv of minuteIntervals" [value]="iv">{{ iv }} min</mat-option>
            </mat-select>
          </mat-form-field>
        </div>

        <div class="time-row" *ngIf="frequency !== 'minutes'">
          <mat-form-field appearance="outline" *ngIf="frequency !== 'hourly'" class="time-field">
            <mat-label>Hour</mat-label>
            <mat-select [(ngModel)]="hour" (ngModelChange)="buildExpression()">
              <mat-option *ngFor="let h of hours" [value]="h.value">{{ h.label }}</mat-option>
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" class="time-field">
            <mat-label>Minute</mat-label>
            <mat-select [(ngModel)]="minute" (ngModelChange)="buildExpression()">
              <mat-option *ngFor="let m of minutes" [value]="m">{{ m | number:'2.0-0' }}</mat-option>
            </mat-select>
          </mat-form-field>
        </div>

        <div class="preview">
          <app-cron-display [expression]="currentExpression"></app-cron-display>
        </div>

        <div class="days-row" *ngIf="frequency === 'weekly'">
          <label class="days-label">Days of the week</label>
          <div class="day-checkboxes">
            <mat-checkbox *ngFor="let day of weekDays"
              [(ngModel)]="day.checked"
              (ngModelChange)="buildExpression()">
              {{ day.label }}
            </mat-checkbox>
          </div>
        </div>

        <div class="day-of-month-row" *ngIf="frequency === 'monthly'">
          <mat-form-field appearance="outline" class="day-field">
            <mat-label>Day of month</mat-label>
            <mat-select [(ngModel)]="dayOfMonth" (ngModelChange)="buildExpression()">
              <mat-option *ngFor="let d of monthDays" [value]="d">{{ d }}</mat-option>
            </mat-select>
          </mat-form-field>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .cron-builder { display: flex; flex-direction: column; gap: 12px; }
    .mode-toggle { display: flex; justify-content: flex-start; }
    .full-width { width: 100%; }
    .frequency-row { display: flex; margin-bottom: 12px; }
    .time-row { display: flex; gap: 12px; }
    .time-field { width: 120px; }
    .days-label { display: block; font-size: 13px; color: #666; margin-bottom: 4px; }
    .day-checkboxes { display: flex; flex-wrap: wrap; gap: 4px 12px; }
    .day-field { width: 160px; }
    .preview { font-size: 13px; color: #666; padding: 4px 0; }
  `],
})
export class CronBuilderComponent implements OnInit, OnDestroy, ControlValueAccessor {
  advancedMode = false;
  rawExpression = '';
  currentExpression = '';

  frequency: Frequency = 'daily';
  hour = 9;
  minute = 0;
  minuteInterval = 15;
  dayOfMonth = 1;

  weekDays: DayOption[] = [
    { label: 'Mon', value: 1, checked: true },
    { label: 'Tue', value: 2, checked: true },
    { label: 'Wed', value: 3, checked: true },
    { label: 'Thu', value: 4, checked: true },
    { label: 'Fri', value: 5, checked: true },
    { label: 'Sat', value: 6, checked: false },
    { label: 'Sun', value: 0, checked: false },
  ];

  hours = Array.from({ length: 24 }, (_, i) => ({
    value: i,
    label: `${i === 0 ? 12 : i > 12 ? i - 12 : i}:00 ${i < 12 ? 'AM' : 'PM'}`,
  }));

  minutes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];
  minuteIntervals = [2, 3, 5, 10, 15, 20, 30];
  monthDays = Array.from({ length: 31 }, (_, i) => i + 1);

  private onChange: (value: string) => void = () => {};
  private onTouched: () => void = () => {};

  ngOnInit() { this.buildExpression(); }
  ngOnDestroy() {}

  writeValue(value: string): void {
    if (!value) return;
    this.currentExpression = value;
    this.rawExpression = value;
    this.parseExpression(value);
  }

  registerOnChange(fn: (value: string) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }

  onModeChange() {
    if (this.advancedMode) {
      this.rawExpression = this.currentExpression;
    } else {
      this.parseExpression(this.rawExpression);
      this.buildExpression();
    }
  }

  onRawChange(value: string) {
    this.currentExpression = value;
    this.onChange(value);
    this.onTouched();
  }

  buildExpression() {
    const min = this.minute;
    switch (this.frequency) {
      case 'minutes':
        this.currentExpression = `*/${this.minuteInterval} * * * *`;
        break;
      case 'hourly':
        this.currentExpression = `${min} * * * *`;
        break;
      case 'daily':
        this.currentExpression = `${min} ${this.hour} * * *`;
        break;
      case 'weekly': {
        const selectedDays = this.weekDays.filter(d => d.checked).map(d => d.value);
        const dayStr = selectedDays.length > 0 ? selectedDays.join(',') : '*';
        this.currentExpression = `${min} ${this.hour} * * ${dayStr}`;
        break;
      }
      case 'monthly':
        this.currentExpression = `${min} ${this.hour} ${this.dayOfMonth} * *`;
        break;
    }
    this.rawExpression = this.currentExpression;
    this.onChange(this.currentExpression);
    this.onTouched();
  }

  private parseExpression(expr: string) {
    if (!expr) return;
    const parts = expr.trim().split(/\s+/);
    if (parts.length !== 5) return;
    const [min, hr, dom, , dow] = parts;
    const stepMatch = min.match(/^\*\/(\d+)$/);
    if (stepMatch && hr === '*') {
      this.frequency = 'minutes';
      this.minuteInterval = parseInt(stepMatch[1], 10);
      return;
    }
    this.minute = this.parseNum(min, 0);
    if (hr === '*') {
      this.frequency = 'hourly';
    } else if (dom !== '*') {
      this.frequency = 'monthly';
      this.hour = this.parseNum(hr, 9);
      this.dayOfMonth = this.parseNum(dom, 1);
    } else if (dow !== '*') {
      this.frequency = 'weekly';
      this.hour = this.parseNum(hr, 9);
      const dayValues = dow.split(',').map(Number).filter(n => !isNaN(n));
      this.weekDays.forEach(d => { d.checked = dayValues.includes(d.value); });
    } else {
      this.frequency = 'daily';
      this.hour = this.parseNum(hr, 9);
    }
  }

  private parseNum(val: string, fallback: number): number {
    const n = parseInt(val, 10);
    return isNaN(n) ? fallback : n;
  }
}
