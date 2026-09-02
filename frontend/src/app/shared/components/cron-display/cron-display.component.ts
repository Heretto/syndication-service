import { Component, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import cronstrue from 'cronstrue';

@Component({
  selector: 'app-cron-display',
  imports: [CommonModule],
  template: `<span class="cron-text" [title]="expression">{{ humanReadable }}</span>`,
  styles: [`
    .cron-text {
      font-size: 12.5px;
      color: #5a6070;
    }
  `],
})
export class CronDisplayComponent implements OnChanges {
  @Input() expression: string | null = '';
  humanReadable = '';

  ngOnChanges(): void {
    if (!this.expression) {
      this.humanReadable = 'Manual sync only';
      return;
    }
    try {
      this.humanReadable = cronstrue.toString(this.expression, { use24HourTimeFormat: false });
    } catch {
      this.humanReadable = this.expression;
    }
  }
}
